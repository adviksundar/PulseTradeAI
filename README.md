# PulseTradeAI

Real-time AI-powered financial intelligence platform for streaming market data, AI news analysis, sentiment scoring, alerts, and WebSocket dashboards.

## What This Skeleton Includes

- FastAPI backend with async background streams.
- WebSocket broadcast server at `/ws/stream`.
- Redis-backed real-time cache with in-memory fallback.
- PostgreSQL-backed MVP event store for ticks, news events, insights, and alerts.
- Mock market and news providers for instant local demos.
- Agent-style analysis pipeline for news, sentiment, risk, and alerts.
- React + TypeScript + Tailwind dashboard with live ticker cards, hourly chart controls, sortable market table, AI insights, alerts, and an agent debug view.
- Docker Compose for Redis, PostgreSQL, backend, and frontend.

## Architecture

```text
Market APIs + News APIs
        |
Async FastAPI Workers
        |
Redis Real-Time Cache
        |
AI Analysis Pipeline
        |
Alert Engine
        |
WebSocket Broadcast Server
        |
React Dashboard
```

## Quick Start

Create environment config:

```bash
cp .env.example .env
```

Start Redis and PostgreSQL:

```bat
docker compose up -d redis postgres
```

Run the backend:

```bash
cd backend
py -m venv .venv
.\.venv\Scripts\activate.bat
py -m pip install -e ".[dev]"
py -m uvicorn app.main:app --reload
```

Run the frontend in another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

## API Surface

- `GET /api/health`: service health plus Redis/PostgreSQL connection status.
- `GET /api/snapshot`: latest cached ticks, AI insights, and alerts.
- `GET /api/market/history/{ticker}?range=1D`: yfinance/mock chart history for `1D`, `5D`, `1M`, `3M`, `1Y`, `5Y`, and `Max`.
- `GET /api/watchlist`: active monitored tickers.
- `POST /api/watchlist`: add validated ticker symbols.
- `DELETE /api/watchlist/{ticker}`: remove a monitored ticker.
- `GET /api/agent-status`: multi-agent workflow status, traces, and debug logs.
- `WS /ws/stream`: real-time stream of `market_tick`, `news_event`, `ai_insight`, and `alert` messages.

## MVP Roadmap

1. Add read/query endpoints for persisted PostgreSQL history.
2. Add provider status and infrastructure status to the dashboard debug view.
3. Add user-configurable alert thresholds and notification channels.
4. Add integration tests for Redis/PostgreSQL-backed workflows.
5. Add deployment notes for EC2/S3 or another cloud target.

## OpenAI Workflow

The backend includes a deterministic multi-agent workflow. To run OpenAI-backed stages, create `.env` from `.env.example` and set:

```env
USE_MOCK_AI=false
OPENAI_API_KEY=your_key_here
OPENAI_FAST_MODEL=gpt-5-nano
OPENAI_BRIEF_MODEL=gpt-5-mini
```

See `docs/MULTI_AGENT_WORKFLOW.md`.

Current model usage is intentionally cost-aware: news analysis and market brief stages call OpenAI once per processed news event, while sentiment, risk, and alert decisions run as local deterministic policy stages.

## Finnhub News

Finnhub company news can be enabled with:

```env
FINNHUB_API_KEY=your_key_here
USE_FINNHUB_NEWS=true
FINNHUB_NEWS_SYMBOLS_PER_POLL=1
FINNHUB_NEWS_MAX_EVENTS_PER_POLL=1
```

The defaults are conservative for the free tier: roughly one Finnhub news request every news poll, about 10 requests per minute with the default `NEWS_POLL_SECONDS=6`.

## FinBERT Sentiment

Optional local transformer sentiment:

```env
SENTIMENT_PROVIDER=finbert
FINBERT_MODEL=ProsusAI/finbert
```

Install AI extras before enabling:

```bash
cd backend
py -m pip install -e ".[ai]"
```

If FinBERT cannot load, the backend automatically falls back to the finance lexicon sentiment scorer.

You can smoke-test local FinBERT setup with:

```bat
cd backend
py scripts\check_finbert.py
```

## Redis and PostgreSQL

For the usual local workflow, run Redis and PostgreSQL in Docker, then run the backend from your Windows virtual environment:

```bat
docker compose up -d redis postgres
cd backend
.\.venv\Scripts\activate.bat
py -m uvicorn app.main:app --reload
```

The backend auto-connects to:

```env
REDIS_URL=redis://localhost:6379/0
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/pulsetradeai
```

Redis is used for fast live snapshots. PostgreSQL stores durable rows in `market_ticks`, `news_events`, `ai_insights`, and `alerts`. If either service is unavailable, the app still starts; Redis falls back to memory and PostgreSQL persistence is disabled until the backend is restarted with Postgres available.

Watchlist changes are also persisted in PostgreSQL. On startup, the backend loads active symbols from `watchlist_symbols`; it uses `TRACKED_TICKERS` from `.env` only when Postgres is unavailable or the watchlist table is empty.
