# Provider Integration Notes

The project starts with mock providers in `backend/app/providers/`.

## Market Data Candidates

- Finnhub: WebSocket trades, company news, basic fundamentals.
- Polygon.io: equities and crypto market data.
- Alpha Vantage: simple REST polling for quotes and indicators.
- yfinance: convenient local/demo data, not ideal for production reliability.

## News Data Candidates

- Finnhub company news.
- Polygon ticker news.
- SEC EDGAR APIs for filings.
- NewsAPI or GDELT for broader market headlines.

## Provider Rules

- Normalize provider-specific payloads into `MarketTick` or `NewsEvent`.
- Fetch and process news only for active dashboard watchlist tickers.
- Keep rate limiting and retries inside provider classes.
- Do not leak provider response shapes into agents or frontend code.
- Keep mock providers available for demos and tests.

## Finnhub Notes

Finnhub is a financial market data API. For PulseTradeAI, it is useful as a next provider because it can supply company news, quote data, and real-time trade streams.

Store the API key in `.env`:

```env
FINNHUB_API_KEY=your_finnhub_key_here
FINNHUB_RATE_LIMIT_PER_MINUTE=60
FINNHUB_MAX_CALLS_PER_SECOND=30
USE_FINNHUB_NEWS=true
FINNHUB_NEWS_SYMBOLS_PER_POLL=1
FINNHUB_NEWS_LOOKBACK_DAYS=7
FINNHUB_NEWS_MAX_EVENTS_PER_POLL=1
FINNHUB_NEWS_BOOTSTRAP_ON_START=true
FINNHUB_NEWS_BOOTSTRAP_SYMBOL_LIMIT=10
FINNHUB_NEWS_BOOTSTRAP_EVENTS_PER_SYMBOL=1
```

Free-tier constraints to design around:

- 60 requests per minute.
- 30 calls per second absolute cap.
- Historical data access is limited; avoid deep backfills on the free tier.
- Premium endpoints such as deeper estimates, transcripts, and revenue breakdowns should stay out of the MVP.

The local API reference file is stored at `docs/reference/finnhub_documentation.json`.

## Current Finnhub Integration

`FinnhubNewsProvider` uses the free-tier `/company-news` endpoint only.

Conservative defaults:

- One company symbol per news poll.
- One news event emitted per poll.
- One startup bootstrap pass can fetch one event for up to 10 company symbols.
- Tickers added later from the dashboard receive a one-event targeted bootstrap.
- Seven-day lookback window.
- At least 1.1 seconds between Finnhub requests.
- Non-company symbols such as `BTC-USD` are skipped for Finnhub company news.
- Non-company symbols such as `BTC-USD` fall back to yfinance/Yahoo Finance news during bootstrap and polling fallback paths.
- If Finnhub or yfinance is missing, unavailable, or errors, the app falls back to the mock news provider.

This keeps the app well below 60 requests per minute during steady-state polling. With the default `NEWS_POLL_SECONDS=6` and `FINNHUB_NEWS_SYMBOLS_PER_POLL=1`, the app makes about 10 Finnhub news requests per minute after the bootstrap completes.
