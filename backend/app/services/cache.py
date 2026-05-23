import json
from collections import defaultdict, deque
from typing import Any

from redis.asyncio import Redis

from app.core.config import Settings
from app.domain.schemas import AIInsight, Alert, DashboardSnapshot, MarketTick
from app.services.persistence import mask_connection_url


class RealtimeCache:
    """Redis cache with an in-memory fallback for local skeleton development."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.redis: Redis | None = None
        self._memory: dict[str, deque[str]] = defaultdict(lambda: deque(maxlen=100))

    async def connect(self) -> None:
        try:
            self.redis = Redis.from_url(self.settings.redis_url, decode_responses=True)
            await self.redis.ping()
        except Exception:
            self.redis = None

    async def close(self) -> None:
        if self.redis:
            await self.redis.aclose()

    def status(self) -> dict[str, object]:
        return {
            "backend": "redis" if self.redis else "memory",
            "connected": self.redis is not None,
            "url": mask_connection_url(self.settings.redis_url),
        }

    async def push_market_tick(self, tick: MarketTick) -> None:
        await self._push("ticks", tick.ticker, tick.model_dump_json(), limit=120)

    async def push_insight(self, insight: AIInsight) -> None:
        await self._push("insights", insight.ticker, insight.model_dump_json(), limit=50)

    async def push_alert(self, alert: Alert) -> None:
        await self._push("alerts", alert.ticker, alert.model_dump_json(), limit=50)
        await self._push("alerts", "all", alert.model_dump_json(), limit=100)

    async def snapshot(self, tickers: list[str]) -> DashboardSnapshot:
        ticks: list[MarketTick] = []
        insights: list[AIInsight] = []
        alerts: list[Alert] = []
        for ticker in tickers:
            ticks.extend(MarketTick.model_validate_json(item) for item in await self._range("ticks", ticker, 0, 4))
            insights.extend(AIInsight.model_validate_json(item) for item in await self._range("insights", ticker, 0, 4))
        alerts.extend(Alert.model_validate_json(item) for item in await self._range("alerts", "all", 0, 19))
        return DashboardSnapshot(ticks=ticks, insights=insights, alerts=alerts)

    async def _push(self, namespace: str, key: str, value: str, limit: int) -> None:
        cache_key = f"pulsetradeai:{namespace}:{key}"
        if self.redis:
            await self.redis.lpush(cache_key, value)
            await self.redis.ltrim(cache_key, 0, limit - 1)
            return
        self._memory[cache_key].appendleft(value)

    async def _range(self, namespace: str, key: str, start: int, stop: int) -> list[str]:
        cache_key = f"pulsetradeai:{namespace}:{key}"
        if self.redis:
            values: list[Any] = await self.redis.lrange(cache_key, start, stop)
            return [str(value) for value in values]
        values = list(self._memory[cache_key])
        return values[start : stop + 1]


def to_ws_payload(event: str, data: Any) -> str:
    if hasattr(data, "model_dump"):
        payload = data.model_dump(mode="json")
    else:
        payload = data
    return json.dumps({"event": event, "data": payload}, default=str)
