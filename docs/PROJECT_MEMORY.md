# Project Memory

This file captures the current build state so future work can resume without rediscovering the same decisions.

## Current Milestone

PulseTradeAI runs locally as a demoable real-time market intelligence app:

- FastAPI backend with async market and news loops.
- React dashboard with live ticker cards, charts, watchlist management, AI insights, alerts, and an agent debug view.
- yfinance-backed market data support with mock-friendly fallbacks.
- yfinance-backed historical chart endpoint for `1D`, `5D`, `1M`, `3M`, `1Y`, `5Y`, and `Max` dashboard ranges.
- Finnhub company-news provider is wired for real news when `FINNHUB_API_KEY` and `USE_FINNHUB_NEWS=true` are set.
- Finnhub news performs one startup bootstrap pass for up to 10 company symbols, then returns to one-symbol-per-poll rotation.
- yfinance/Yahoo news is used as a fallback for non-company symbols such as `BTC-USD`, with mock news underneath as a final fallback.
- News providers now sanitize malformed article text and require ticker/company relevance before an item can enter the AI workflow, reducing unrelated high-confidence insights from broad finance headlines.
- Tickers added from the dashboard mid-session trigger a targeted quote/news bootstrap so they can receive an initial AI insight without waiting for the normal news rotation.
- News processing is watchlist-scoped: only tickers currently tracked by the dashboard should enter the AI pipeline or WebSocket broadcasts.
- Startup and mid-session news bootstrap now processes ticker-by-ticker so the first completed ticker can produce an AI insight before the entire watchlist finishes.
- Sentiment analysis supports optional FinBERT via `SENTIMENT_PROVIDER=finbert`, with the finance lexicon scorer as fallback when HuggingFace dependencies/model loading are unavailable.
- Redis is used as the hot real-time cache when Docker Redis is running, with the previous in-memory fallback still available.
- PostgreSQL persistence is now wired through `EventStore`; it auto-creates MVP tables and stores market ticks, news events, AI insights, and alerts when Docker Postgres is running.
- PostgreSQL market volume columns use `BIGINT` and startup migration corrects earlier `INTEGER` columns because crypto/equity volume can exceed 32-bit integer range.
- Watchlist changes now persist in PostgreSQL via `watchlist_symbols`; on startup the backend loads the active DB watchlist and seeds from `.env` only when the table is empty or Postgres is unavailable.
- Generated packaging output (`*.egg-info`) is ignored, and the FinBERT smoke test lives in `backend/scripts/check_finbert.py`.
- README and multi-agent docs now describe the current Redis/PostgreSQL and FinBERT-backed workflow accurately before the initial commit.

Recent operational notes (May 2026):

- FinBERT integration hardened: thread-safety, device detection, and robust output parsing were added to avoid runtime "shape" and race errors when the pipeline is initialized concurrently.
- Confidence model: FinBERT confidence uses the model's top-class probability capped to the UI range, while lexicon scores are normalized and calibrated so confidence values remain meaningful (0.0-1.0) and avoid extreme overconfidence on short headlines.
- Provenance and raw scores: `SentimentOutput` now stores `raw_score` and `source`, and the API-level `AIInsight` includes `sentiment_source` and `raw_sentiment_score` for traceability.
- NLP boundary: FinBERT classifies article/news language only. Market movement and volume are handled by risk scoring so price action does not leak into text sentiment classification.
- Frontend alignment: the dashboard `SentimentTile` uses the normalized `confidence` field (0-1) for heatmaps and percent displays; previously the tile mixed signed `sentiment_score` with confidence causing 0.00 displays on neutrals.
- OpenAI reliability: news-analysis requests now send `article_excerpt` (token/char trimmed), compact JSON payloads, minimal GPT-5 reasoning, compact retry instructions, and larger structured-output budgets to reduce token costs and decrease empty/truncated JSON responses.
- OpenAI diagnostics: empty structured outputs now log compact response diagnostics (`status`, incomplete reason, output types, usage) instead of dumping a very large raw response payload.
- News relevance: yfinance/Yahoo and Finnhub items are filtered against ticker aliases (for example AAPL/Apple, MSFT/Microsoft, NVDA/NVIDIA, BTC/Bitcoin) before processing. If no relevant real article is found for targeted bootstrap, the mock fallback can still provide a demo insight.
- Optional tiktoken: token-aware trimming is used when `tiktoken` is installed; otherwise character-based excerpting is used as a fallback.
- Mock news provider that emits demo financial events on a poll interval.
- OpenAI-backed workflow for news extraction and market brief generation when `USE_MOCK_AI=false`.
- Deterministic local policy stages for sentiment, risk scoring, and alert decisions to keep cost low and behavior predictable.

## Agent Workflow Behavior

Each news event is processed once through this controlled pipeline:

```text
News event
-> News Analysis Agent
-> Sentiment Analysis Agent
-> Risk Scoring Agent
-> Alert Decision Agent
-> Market Brief Agent
-> Redis cache and PostgreSQL event store
-> WebSocket dashboard
```

Current OpenAI usage:

- News Analysis: one OpenAI structured-output call per processed news event.
- Market Brief: one OpenAI structured-output call per processed news event.
- Sentiment, Risk, Alert Decision: local backend policy, zero OpenAI calls.

In the debug UI, stage cards focus on "Since startup" counts. Recent-event logs still exist below the graph for per-event debugging.

## Dashboard Chart Behavior

The price chart now supports `Live`, `1D`, `5D`, `1M`, `3M`, `1Y`, `5Y`, and `Max`.

- `Live` uses ticks collected by the running backend process.
- Historical ranges call `/api/market/history/{ticker}`.
- yfinance provides real history when available.
- Mock fallback generates plausible history when yfinance is unavailable.

The volume panel compares the latest backend tick for each visible ticker:

- `Log volume`: log-scaled latest volume for cross-asset comparison.
- `Volume`: raw latest volume.
- `Day move`: latest price versus previous close when yfinance data is available.

The market table controls are sort controls, not filters. They reorder visible tickers by absolute day move, latest volume, newest quote refresh, or ticker symbol.

If a range looks flat, check whether the selected ticker has real historical data from yfinance and whether the backend is running with `USE_MOCK_MARKET_DATA=false`.

## Local Run Notes

Start infrastructure with Docker Desktop running:

```bat
docker compose up -d redis postgres
```

Check infrastructure status after the backend starts:

```text
http://localhost:8000/api/health
```

Backend on Windows:

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

Open the dashboard at `http://localhost:5173`.

## Next Useful Work

- Add provider status to the dashboard/debug page so it is obvious whether Finnhub or mock news is active.
- Consider Finnhub quote support later, but keep yfinance as the quote provider for now to avoid burning free-tier calls across the watchlist.
- Add read/query endpoints for persisted PostgreSQL history.
- Add user-configurable alert thresholds.
- Add chart/table preferences to local storage.
- Add backend tests for agent state, watchlist validation, `/api/agent-status`, and `/api/market/history/{ticker}`.
