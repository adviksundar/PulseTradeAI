from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import os

from fastapi import FastAPI, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.agents.alert_decision import AlertDecisionAgent
from app.agents.workflow.orchestrator import FinancialIntelligenceOrchestrator
from app.api.routes import router
from app.core.config import get_settings
from app.providers.market import MockMarketDataProvider, YFinanceMarketDataProvider
from app.providers.news import FinnhubNewsProvider, MockNewsProvider, YFinanceNewsProvider
from app.services.cache import RealtimeCache
from app.services.persistence import EventStore
from app.services.websocket_manager import WebSocketManager
from app.workers.streams import StreamOrchestrator


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    # Ensure Hugging Face libraries can read token from process env, even when
    # token is configured via app .env/settings.
    if settings.hf_token:
        os.environ.setdefault("HF_TOKEN", settings.hf_token)
        os.environ.setdefault("HUGGINGFACE_HUB_TOKEN", settings.hf_token)
    cache = RealtimeCache(settings)
    event_store = EventStore(settings)
    websockets = WebSocketManager()
    await cache.connect()
    await event_store.connect()
    settings.tracked_tickers = await event_store.load_watchlist(settings.tracked_tickers)

    intelligence_orchestrator = FinancialIntelligenceOrchestrator(settings)
    mock_news_provider = MockNewsProvider()
    yahoo_news_provider = YFinanceNewsProvider(fallback=mock_news_provider)
    news_provider = (
        FinnhubNewsProvider(settings, fallback=yahoo_news_provider)
        if settings.use_finnhub_news and settings.finnhub_api_key
        else yahoo_news_provider
    )
    orchestrator = StreamOrchestrator(
        settings=settings,
        market_provider=YFinanceMarketDataProvider()
        if not settings.use_mock_market_data
        else MockMarketDataProvider(),
        news_provider=news_provider,
        intelligence_orchestrator=intelligence_orchestrator,
        alert_agent=AlertDecisionAgent(settings),
        cache=cache,
        event_store=event_store,
        websockets=websockets,
    )
    app.state.settings = settings
    app.state.cache = cache
    app.state.event_store = event_store
    app.state.websockets = websockets
    app.state.intelligence_orchestrator = intelligence_orchestrator
    app.state.stream_orchestrator = orchestrator
    orchestrator.start()
    try:
        yield
    finally:
        await orchestrator.stop()
        await cache.close()
        await event_store.close()


app = FastAPI(title="PulseTradeAI API", version="0.1.0", lifespan=lifespan)
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router, prefix="/api")


@app.get("/")
async def root() -> dict[str, object]:
    return {
        "name": "PulseTradeAI API",
        "status": "ok",
        "docs": "/docs",
        "health": "/api/health",
        "snapshot": "/api/snapshot",
        "market_history": "/api/market/history/AAPL?range=1D",
        "stream": "/ws/stream",
    }


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> Response:
    return Response(status_code=204)


@app.websocket("/ws/stream")
async def market_stream(websocket: WebSocket) -> None:
    manager: WebSocketManager = websocket.app.state.websockets
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
