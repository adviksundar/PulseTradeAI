import asyncio
import re

from fastapi import APIRouter, Request

from app.domain.schemas import DashboardSnapshot, MarketHistory, Watchlist, WatchlistUpdate

router = APIRouter()
TICKER_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9.-]{0,15}$")
HISTORY_RANGES = {"1D", "5D", "1M", "3M", "1Y", "5Y", "Max"}


@router.get("/")
async def api_index() -> dict[str, object]:
    return {
        "name": "PulseTradeAI API",
        "status": "ok",
        "routes": {
            "health": "/api/health",
            "snapshot": "/api/snapshot",
            "market_history": "/api/market/history/{ticker}?range=1D",
            "watchlist": "/api/watchlist",
            "stream": "/ws/stream",
        },
    }


@router.get("/health")
async def health(request: Request) -> dict[str, object]:
    cache = getattr(request.app.state, "cache", None)
    event_store = getattr(request.app.state, "event_store", None)
    return {
        "status": "ok",
        "redis": cache.status() if cache else None,
        "postgres": event_store.status() if event_store else None,
    }


@router.get("/agent-status")
async def agent_status(request: Request) -> dict[str, object]:
    orchestrator = getattr(request.app.state, "intelligence_orchestrator", None)
    stream = getattr(request.app.state, "stream_orchestrator", None)
    latest_state = orchestrator.state_history[0] if orchestrator and orchestrator.state_history else None
    settings = request.app.state.settings
    stage_definitions = [
        {
            "agent": "news_analysis",
            "label": "News Analysis",
            "description": "Extracts summary, key event, company, impact, and keywords.",
            "uses_openai": True,
            "model": settings.openai_fast_model,
        },
        {
            "agent": "sentiment",
            "label": "Sentiment",
            "description": "Classifies bullish, neutral, or bearish sentiment using deterministic rules.",
            "uses_openai": False,
            "model": "deterministic",
        },
        {
            "agent": "risk",
            "label": "Risk Scoring",
            "description": "Scores market risk from sentiment, price movement, and volume anomaly.",
            "uses_openai": False,
            "model": "deterministic",
        },
        {
            "agent": "alert_decision",
            "label": "Alert Decision",
            "description": "Applies deterministic alert policy and urgency level.",
            "uses_openai": False,
            "model": "deterministic",
        },
        {
            "agent": "market_brief",
            "label": "Market Brief",
            "description": "Generates a short dashboard-ready market intelligence brief.",
            "uses_openai": True,
            "model": settings.openai_brief_model,
        },
    ]
    return {
        "openai_enabled": bool(settings.openai_api_key and not settings.use_mock_ai),
        "use_mock_ai": settings.use_mock_ai,
        "fast_model": settings.openai_fast_model,
        "brief_model": settings.openai_brief_model,
        "processed_events": len(orchestrator.state_history) if orchestrator else 0,
        "total_openai_attempts": orchestrator.client.total_call_count if orchestrator else 0,
        "total_openai_successes": orchestrator.client.total_success_count if orchestrator else 0,
        "total_openai_calls": orchestrator.client.total_success_count if orchestrator else 0,
        "stage_call_counts": orchestrator.stage_call_counts if orchestrator else {},
        "stage_success_counts": orchestrator.stage_success_counts if orchestrator else {},
        "latest_completed_at": latest_state.normalized_at.isoformat() if latest_state else None,
        "news_poll_seconds": settings.news_poll_seconds,
        "market_poll_seconds": settings.market_poll_seconds,
        "news_loop_count": stream.news_loop_count if stream else 0,
        "news_events_seen": stream.news_events_seen if stream else 0,
        "market_loop_count": stream.market_loop_count if stream else 0,
        "last_news_loop_started_at": stream.last_news_loop_started_at.isoformat()
        if stream and stream.last_news_loop_started_at
        else None,
        "last_news_loop_completed_at": stream.last_news_loop_completed_at.isoformat()
        if stream and stream.last_news_loop_completed_at
        else None,
        "last_news_event_at": stream.last_news_event_at.isoformat() if stream and stream.last_news_event_at else None,
        "last_market_loop_at": stream.last_market_loop_at.isoformat() if stream and stream.last_market_loop_at else None,
        "stage_definitions": stage_definitions,
        "latest_trace": [item.model_dump(mode="json") for item in latest_state.trace] if latest_state else [],
        "latest_ticker": latest_state.ticker if latest_state else None,
        "latest_headline": latest_state.headline if latest_state else None,
        "recent_events": [
            {
                "event_id": state.event_id,
                "ticker": state.ticker,
                "headline": state.headline,
                "timestamp": state.timestamp.isoformat(),
                "trace": [item.model_dump(mode="json") for item in state.trace],
            }
            for state in (orchestrator.state_history[:10] if orchestrator else [])
        ],
        "logs": orchestrator.workflow_logs[:50] if orchestrator else [],
    }


@router.get("/snapshot", response_model=DashboardSnapshot)
async def snapshot(request: Request) -> DashboardSnapshot:
    return await request.app.state.cache.snapshot(request.app.state.settings.tracked_tickers)


@router.get("/market/history/{ticker}", response_model=MarketHistory)
async def market_history(request: Request, ticker: str, range: str = "1D") -> MarketHistory:
    normalized = normalize_ticker(ticker)
    range_name = range if range in HISTORY_RANGES else "1D"
    return await request.app.state.stream_orchestrator.market_provider.get_history(normalized, range_name)


@router.get("/watchlist", response_model=Watchlist)
async def get_watchlist(request: Request) -> Watchlist:
    return Watchlist(tickers=request.app.state.settings.tracked_tickers)


@router.post("/watchlist", response_model=Watchlist)
async def add_to_watchlist(request: Request, update: WatchlistUpdate) -> Watchlist:
    existing = request.app.state.settings.tracked_tickers
    seen = set(existing)
    rejected: list[str] = []
    added: list[str] = []
    for ticker in update.tickers:
        normalized = normalize_ticker(ticker)
        if not normalized or normalized in seen:
            continue
        if not await is_valid_ticker(normalized, request.app.state.settings.use_mock_market_data):
            rejected.append(normalized or ticker)
            continue
        if normalized not in seen:
            existing.append(normalized)
            seen.add(normalized)
            added.append(normalized)
    if added:
        await request.app.state.event_store.add_watchlist_symbols(added)
        asyncio.create_task(request.app.state.stream_orchestrator.bootstrap_news_for_tickers(added))
    return Watchlist(tickers=existing, rejected=rejected)


@router.delete("/watchlist/{ticker}", response_model=Watchlist)
async def remove_from_watchlist(request: Request, ticker: str) -> Watchlist:
    normalized = normalize_ticker(ticker)
    request.app.state.settings.tracked_tickers = [
        current for current in request.app.state.settings.tracked_tickers if current != normalized
    ]
    await request.app.state.event_store.remove_watchlist_symbol(normalized)
    return Watchlist(tickers=request.app.state.settings.tracked_tickers)


def normalize_ticker(value: str) -> str:
    return value.strip().upper().replace(" ", "")


async def is_valid_ticker(ticker: str, allow_syntax_only: bool) -> bool:
    if not TICKER_PATTERN.fullmatch(ticker):
        return False
    if allow_syntax_only:
        return True
    try:
        return await asyncio.to_thread(has_yfinance_quote, ticker)
    except Exception:
        return False


def has_yfinance_quote(ticker: str) -> bool:
    import yfinance as yf

    yahoo_ticker = yf.Ticker(ticker)
    try:
        fast_info = yahoo_ticker.fast_info
        price = fast_info.get("last_price") or fast_info.get("lastPrice")
        if price and float(price) > 0:
            return True
    except Exception:
        pass

    history = yahoo_ticker.history(period="5d", interval="1d")
    return not history.empty
