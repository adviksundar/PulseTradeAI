# PulseTradeAI

Real-time AI-powered financial intelligence platform for streaming market data, AI news analysis, sentiment scoring, alerts, and WebSocket dashboards.

## Demo

Main dashboard:

<video src="videos/PulseTradeAI_Dashboard_Recording_1.mp4" controls muted playsinline width="720"></video>

[View dashboard video](videos/PulseTradeAI_Dashboard_Recording_1.mp4)

Agent debug dashboard:

<video src="videos/PulseTradeAI_Debug_Dashboard_Recording_1.mp4" controls muted playsinline width="720"></video>

[View debug dashboard video](videos/PulseTradeAI_Debug_Dashboard_Recording_1.mp4)

## What It Includes

- FastAPI backend with async market and news workers.
- WebSocket broadcast server at `/ws/stream`.
- Redis-backed hot cache with an in-memory fallback.
- PostgreSQL-backed event store for ticks, news events, insights, alerts, and watchlist state.
- yfinance market data and history, Finnhub company news, Yahoo/yfinance news fallback, and mock providers for local demos.
- Deterministic graph-style AI workflow with OpenAI structured extraction/briefing and optional FinBERT sentiment.
- React + TypeScript + Tailwind dashboard with live ticker cards, configurable charts, sortable market table, AI insights, alerts, portfolio upload, and an agent debug view.
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

## Tech Stack Decisions

- **FastAPI + asyncio**: keeps the backend lightweight while supporting concurrent market polling, news ingestion, AI workflow execution, and WebSocket broadcasts.
- **React + TypeScript**: provides a typed dashboard surface for real-time UI state, chart controls, watchlist management, and debug views.
- **WebSockets**: push market ticks, news events, AI insights, alerts, and agent state to the browser without forcing constant polling.
- **Redis**: used as a hot real-time cache for recent ticks, insights, and alerts. Redis is a good fit for low-latency dashboard snapshots and short-lived streaming state.
- **PostgreSQL**: used as durable storage for event history and watchlist state. PostgreSQL is a good fit for relational records, indexing, and structured queries over ticks, alerts, and AI outputs.
- **Why Redis and Postgres together**: Redis optimizes the live dashboard path; Postgres preserves durable history. Using only Postgres would make the live snapshot path heavier, while using only Redis would make historical analysis and persisted watchlists fragile.
- **OpenAI structured outputs**: used where language reasoning is valuable: news extraction and short market briefs.
- **FinBERT**: used locally for financial sentiment classification to reduce OpenAI cost and keep sentiment scoring explainable and provider-independent.
- **Docker Compose**: runs Redis and PostgreSQL consistently across machines without requiring manual database installs.

## Agent Architecture

PulseTradeAI uses a deterministic sequential agent workflow controlled by a central orchestrator. It is intentionally not a fully autonomous agent system.

```text
News Event
  -> News Analysis Agent
  -> Sentiment Analysis Agent
  -> Risk Scoring Agent
  -> Alert Decision Agent
  -> Market Brief Agent
  -> Redis/PostgreSQL
  -> WebSocket Dashboard
```

The orchestrator owns routing, ordering, retries, shared state, traces, and broadcast side effects. Each agent has one responsibility and appends structured output to a shared `FinancialEventState`.

This pattern was chosen because financial intelligence workflows need predictable execution, auditable state transitions, and low-latency behavior. A sequential graph is less flexible than a free-form coordinator, but it is easier to debug, test, and explain. The dashboard debug view exposes stage status, OpenAI call counts, recent event traces, and fallback behavior.

## Token and Cost Control

The workflow avoids calling an LLM for every stage.

- News analysis uses OpenAI structured outputs for concise event extraction.
- Sentiment runs locally with FinBERT when enabled, falling back to a finance lexicon scorer.
- Risk scoring and alert decisions run as deterministic backend policy.
- Market briefs use OpenAI only after prior stages have produced compact structured state.

Prompt payloads are compacted before OpenAI calls. News article text is trimmed into an `article_excerpt`; when `tiktoken` is installed, the backend uses OpenAI-compatible byte pair encoding tokenization to cap prompt size more predictably than character-only truncation. This reduces token usage, lowers cost, and helps prevent structured JSON responses from being truncated.

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

## Implemented Capabilities

- Live market polling with yfinance and mock fallbacks.
- Company-news ingestion with Finnhub, Yahoo/yfinance fallback news, ticker relevance filtering, and free-tier conscious rate limiting.
- Watchlist add/remove workflows with ticker validation, targeted news bootstrap, and PostgreSQL persistence across sessions.
- Sequential agent workflow for news extraction, sentiment analysis, risk scoring, alert decisions, and market briefs.
- OpenAI structured outputs for news analysis and market brief generation.
- Optional local FinBERT sentiment classification with finance-lexicon fallback.
- Redis-backed live cache for fast dashboard snapshots.
- PostgreSQL event storage for ticks, news events, AI insights, alerts, and active watchlist symbols.
- WebSocket streaming for market ticks, news events, insights, alerts, and agent state.
- React dashboard with ticker cards, configurable charts, volume/move comparisons, sentiment heatmap, alerts, AI insights, portfolio upload, and agent debug view.
- Docker Compose setup for Redis and PostgreSQL.

## OpenAI Workflow

The backend includes a deterministic multi-agent workflow. To run OpenAI-backed stages, create `.env` from `.env.example` and set:

```env
USE_MOCK_AI=false
OPENAI_API_KEY=your_key_here
OPENAI_FAST_MODEL=gpt-5-nano
OPENAI_BRIEF_MODEL=gpt-5-mini
```

See `docs/MULTI_AGENT_WORKFLOW.md`.

Current model usage is intentionally cost-aware: news analysis and market brief stages call OpenAI once per processed news event, sentiment can run locally with FinBERT, and risk/alert decisions run as deterministic policy stages.

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
