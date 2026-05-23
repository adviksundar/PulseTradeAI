# Architecture

PulseTradeAI uses a lightweight event-driven architecture that can run locally but resembles a production financial intelligence pipeline.

## Runtime Flow

1. Market and news providers emit normalized domain events.
2. `StreamOrchestrator` runs async loops for market ticks and news.
3. Market ticks are cached, persisted when PostgreSQL is available, and broadcast immediately.
4. News events flow through `NewsAnalysisAgent`.
5. `AlertDecisionAgent` evaluates market movement, volume, breaking news, and sentiment shifts.
6. Redis stores recent real-time state for fast dashboard snapshots.
7. PostgreSQL stores durable MVP history for ticks, news events, AI insights, and alerts.
8. WebSocket clients receive low-latency updates.

## Storage

- Redis is the hot cache for dashboard snapshots and live state. If Redis is unavailable, `RealtimeCache` falls back to in-memory storage so local demos still run.
- PostgreSQL is the durable event store. `EventStore` auto-creates MVP tables on startup and silently disables persistence if the database is unavailable.
- The active watchlist is stored in PostgreSQL. `.env` tickers act as the seed/default list rather than the long-term source of truth once Postgres is available.
- `/api/health` reports whether Redis and PostgreSQL are connected, with connection URLs masked.

## Market Data Modes

The dashboard has two market-data paths:

- Live ticks: `StreamOrchestrator` polls the active market provider, updates cache, and broadcasts `market_tick` WebSocket messages.
- Historical ranges: `GET /api/market/history/{ticker}` returns chart points for `1D`, `5D`, `1M`, `3M`, `1Y`, `5Y`, and `Max`.

yfinance is used for real quote/history data when mock market mode is off. Mock providers still generate usable ticks and history for local demos without external dependencies.

## Core Contracts

Domain contracts live in `backend/app/domain/schemas.py`:

- `MarketTick`
- `MarketHistory`
- `MarketHistoryPoint`
- `NewsEvent`
- `AIInsight`
- `Alert`
- `DashboardSnapshot`

Keep these contracts stable and version them deliberately once external clients depend on them.

## AI Pipeline

The initial implementation uses deterministic mock analysis so the app can run without API keys. The intended production path is:

```text
NewsEvent
  -> OpenAI structured summarization
  -> FinBERT or OpenAI sentiment classification
  -> risk scoring
  -> alert decision
```

## Scaling Path

- Start: FastAPI background tasks, Redis cache, PostgreSQL persistence.
- Next: dedicated worker processes for ingestion and AI analysis.
- Later: Kafka or Redpanda topics for ticks, news, insights, and alerts.
- Advanced: vector search/RAG for filings and analyst commentary.
