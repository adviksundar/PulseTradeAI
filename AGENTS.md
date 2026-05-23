# PulseTradeAI Agent Guide

This file is the quick operating guide for AI/code agents working in this repo. Keep it short and route deeper context to the docs below.

## Start Here

- Current project status and decisions: `docs/PROJECT_MEMORY.md`
- System architecture: `docs/ARCHITECTURE.md`
- Multi-agent workflow behavior and debug counters: `docs/MULTI_AGENT_WORKFLOW.md`
- AI pipeline and cost profile: `docs/AI_PIPELINE.md`
- Market/news provider notes: `docs/PROVIDERS.md`
- User-facing setup and endpoints: `README.md`

## Mission

PulseTradeAI is a real-time AI market intelligence platform:

```text
Market/news providers -> async workers -> cache -> AI analysis -> alert decisions -> WebSocket dashboard
```

## Engineering Rules

- Prefer async interfaces for ingestion, cache, AI, and broadcast paths.
- Keep provider integrations swappable. Mock providers must remain useful for local demos and tests.
- Keep shared backend contracts in `backend/app/domain/schemas.py`.
- Treat Redis as a real-time cache, not long-term truth.
- Add PostgreSQL persistence behind services/repositories when historical storage becomes necessary.
- Keep frontend work focused on live scanning, comparison, alerts, drill-downs, and debugging.
- Put durable project memory in `docs/PROJECT_MEMORY.md`; put private scratch notes in ignored local files.
- Whenever behavior, architecture, providers, agents, config, workflow, setup, or UI meaningfully changes, update `docs/PROJECT_MEMORY.md` in the same work pass.

## Layout

- Backend app: `backend/app/`
- API routes: `backend/app/api/routes.py`
- Domain schemas: `backend/app/domain/schemas.py`
- Providers: `backend/app/providers/`
- Agent workflow: `backend/app/agents/workflow/`
- Streaming workers: `backend/app/workers/`
- Frontend dashboard: `frontend/src/App.tsx`
- Frontend API/types: `frontend/src/api.ts`, `frontend/src/types.ts`

## Windows Run Commands

Backend:

```bat
cd backend
py -m venv .venv
.\.venv\Scripts\activate.bat
py -m pip install -e ".[dev]"
py -m uvicorn app.main:app --reload
```

Frontend:

```bat
cd frontend
npm install
npm run dev
```

## Testing Guidance

- Add unit tests for agents, watchlist validation, alert thresholds, and history range mapping.
- Add integration tests for `/api/snapshot`, `/api/agent-status`, `/api/market/history/{ticker}`, and `/ws/stream`.
- Keep external provider tests mocked unless explicitly running live-provider smoke tests.

## Recent Agent Changes (May 2026)

- Sentiment Agent: optional FinBERT support was hardened (thread-safe lazy load, device detection, robust output parsing) and now emits provenance (`raw_score`, `source`).
- News Analysis Agent: payloads are compacted and trimmed to `article_excerpt` (token-aware when `tiktoken` available), and structured OpenAI calls request minimal reasoning to reduce token cost and empty JSON responses.
- Orchestrator: AI insights include `sentiment_source` and `raw_sentiment_score` so UIs and downstream rules can choose canonical signals or surface provenance to users.
