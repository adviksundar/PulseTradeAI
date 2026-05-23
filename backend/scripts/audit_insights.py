import asyncio
import statistics
from collections import defaultdict
from datetime import datetime, timezone

from app.core.config import get_settings
from app.services.cache import RealtimeCache


async def main():
    settings = get_settings()
    cache = RealtimeCache(settings)
    await cache.connect()
    snapshot = await cache.snapshot(settings.tracked_tickers)

    insights = snapshot.insights
    if not insights:
        print("No cached insights found (Redis not running or backend not active).")
        return

    by_ticker = defaultdict(list)
    for ins in insights:
        by_ticker[ins.ticker].append(ins)

    summary = {}
    now = datetime.now(timezone.utc)
    for ticker, items in by_ticker.items():
        confidences = [i.confidence for i in items if i.confidence is not None]
        labels = [i.sentiment for i in items]
        recent = sorted(items, key=lambda item: item.created_at, reverse=True)[:5]
        # conflicts: presence of both Bullish and Bearish in recent 5
        has_bull = any(l.lower() == "bullish" or l.lower()
                       == "positive" for l in labels)
        has_bear = any(l.lower() == "bearish" or l.lower()
                       == "negative" for l in labels)
        conflict = has_bull and has_bear
        summary[ticker] = {
            "count": len(items),
            "mean_confidence": statistics.mean(confidences) if confidences else None,
            "min_confidence": min(confidences) if confidences else None,
            "max_confidence": max(confidences) if confidences else None,
            "recent_labels": [f"{r.sentiment} ({r.confidence})" for r in recent],
            "conflict": conflict,
            "sources": list({r.sentiment_source for r in items if r.sentiment_source}),
        }

    # global stats
    all_conf = [i.confidence for i in insights if i.confidence is not None]
    global_stats = {
        "total_insights": len(insights),
        "mean_confidence": statistics.mean(all_conf) if all_conf else None,
        "min_confidence": min(all_conf) if all_conf else None,
        "max_confidence": max(all_conf) if all_conf else None,
    }

    import json
    print(json.dumps({"global": global_stats,
          "by_ticker": summary}, default=str, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
