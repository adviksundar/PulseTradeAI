import asyncio
from contextlib import suppress

from app.agents.alert_decision import AlertDecisionAgent
from app.agents.workflow.orchestrator import FinancialIntelligenceOrchestrator
from app.core.config import Settings
from app.domain.schemas import MarketTick, NewsEvent
from app.domain.schemas import utc_now
from app.providers.market import MarketDataProvider
from app.providers.news import NewsProvider
from app.services.cache import RealtimeCache
from app.services.persistence import EventStore
from app.services.websocket_manager import WebSocketManager


class StreamOrchestrator:
    def __init__(
        self,
        settings: Settings,
        market_provider: MarketDataProvider,
        news_provider: NewsProvider,
        intelligence_orchestrator: FinancialIntelligenceOrchestrator,
        alert_agent: AlertDecisionAgent,
        cache: RealtimeCache,
        event_store: EventStore,
        websockets: WebSocketManager,
    ) -> None:
        self.settings = settings
        self.market_provider = market_provider
        self.news_provider = news_provider
        self.intelligence_orchestrator = intelligence_orchestrator
        self.alert_agent = alert_agent
        self.cache = cache
        self.event_store = event_store
        self.websockets = websockets
        self._tasks: list[asyncio.Task[None]] = []
        self._latest_ticks: dict[str, MarketTick] = {}
        self.market_loop_count = 0
        self.news_loop_count = 0
        self.news_events_seen = 0
        self.last_market_loop_at = None
        self.last_news_loop_started_at = None
        self.last_news_loop_completed_at = None
        self.last_news_event_at = None
        self._startup_bootstrap_done: asyncio.Event | None = None

    def start(self) -> None:
        self._startup_bootstrap_done = asyncio.Event()
        self._tasks = [
            asyncio.create_task(self._startup_news_bootstrap(), name="news-bootstrap"),
            asyncio.create_task(self._market_loop(), name="market-stream"),
            asyncio.create_task(self._news_loop(), name="news-stream"),
        ]

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with suppress(asyncio.CancelledError):
                await task

    async def _market_loop(self) -> None:
        while True:
            self.market_loop_count += 1
            self.last_market_loop_at = utc_now()
            for ticker in list(self.settings.tracked_tickers):
                tick = await self.market_provider.get_tick(ticker)
                self._latest_ticks[ticker] = tick
                await self.cache.push_market_tick(tick)
                await self.event_store.save_market_tick(tick)
                await self.websockets.broadcast("market_tick", tick)
                for alert in await self.alert_agent.from_tick(tick):
                    await self.cache.push_alert(alert)
                    await self.event_store.save_alert(alert)
                    await self.websockets.broadcast("alert", alert)
            await asyncio.sleep(self.settings.market_poll_seconds)

    async def _news_loop(self) -> None:
        if self._startup_bootstrap_done is not None:
            await self._startup_bootstrap_done.wait()
        while True:
            self.news_loop_count += 1
            self.last_news_loop_started_at = utc_now()
            events = await self.news_provider.get_latest(list(self.settings.tracked_tickers))
            self.news_events_seen += len(events)
            for event in events:
                await self._process_news_event(event)
            self.last_news_loop_completed_at = utc_now()
            await asyncio.sleep(self.settings.news_poll_seconds)

    async def _startup_news_bootstrap(self) -> None:
        try:
            if not self.settings.tracked_tickers:
                return
            await self.bootstrap_news_for_tickers(list(self.settings.tracked_tickers))
            self.news_provider.mark_bootstrap_complete()
        finally:
            if self._startup_bootstrap_done is not None:
                self._startup_bootstrap_done.set()

    async def bootstrap_news_for_tickers(self, tickers: list[str]) -> None:
        if not tickers:
            return
        normalized = [ticker for ticker in tickers if ticker in self.settings.tracked_tickers]
        if not normalized:
            return
        for ticker in normalized:
            if ticker not in self._latest_ticks:
                tick = await self.market_provider.get_tick(ticker)
                self._latest_ticks[ticker] = tick
                await self.cache.push_market_tick(tick)
                await self.event_store.save_market_tick(tick)
                await self.websockets.broadcast("market_tick", tick)
            events = await self.news_provider.get_for_ticker(ticker, max_items=1)
            self.news_events_seen += len(events)
            for event in events:
                await self._process_news_event(event)

    async def _process_news_event(self, event: NewsEvent) -> None:
        if event.ticker not in self.settings.tracked_tickers:
            return
        self.last_news_event_at = utc_now()
        await self.event_store.save_news_event(event)
        await self.websockets.broadcast("news_event", event)
        state, insight, workflow_alert = await self.intelligence_orchestrator.process_news_event(
            event,
            self._latest_ticks.get(event.ticker),
        )
        await self.cache.push_insight(insight)
        await self.event_store.save_insight(insight)
        await self.websockets.broadcast("ai_insight", insight)
        await self.websockets.broadcast("agent_state", state)
        if workflow_alert:
            await self.cache.push_alert(workflow_alert)
            await self.event_store.save_alert(workflow_alert)
            await self.websockets.broadcast("alert", workflow_alert)
