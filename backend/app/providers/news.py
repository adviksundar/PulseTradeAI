import itertools
import random
import re
import unicodedata
from datetime import UTC, datetime, timedelta

import httpx

from app.core.config import Settings
from app.domain.schemas import NewsEvent


TICKER_ALIASES: dict[str, tuple[str, ...]] = {
    "AAPL": ("aapl", "apple"),
    "MSFT": ("msft", "microsoft"),
    "NVDA": ("nvda", "nvidia"),
    "TSLA": ("tsla", "tesla"),
    "BTC-USD": ("btc", "bitcoin"),
    "ETH-USD": ("eth", "ethereum"),
    "META": ("meta", "facebook"),
    "GOOGL": ("googl", "google", "alphabet"),
    "GOOG": ("goog", "google", "alphabet"),
    "AMD": ("amd", "advanced micro devices"),
    "INTC": ("intc", "intel"),
    "AMZN": ("amzn", "amazon"),
    "F": ("f", "ford"),
    "GM": ("gm", "general motors"),
}


class NewsProvider:
    async def get_latest(self, tickers: list[str]) -> list[NewsEvent]:
        raise NotImplementedError

    async def get_for_ticker(self, ticker: str, max_items: int = 1) -> list[NewsEvent]:
        return await self.get_latest([ticker])

    async def bootstrap_for_tickers(self, tickers: list[str], max_items_per_ticker: int = 1) -> list[NewsEvent]:
        events: list[NewsEvent] = []
        for ticker in tickers:
            events.extend(await self.get_for_ticker(ticker, max_items=max_items_per_ticker))
        return events

    def mark_bootstrap_complete(self) -> None:
        return None


class MockNewsProvider(NewsProvider):
    def __init__(self) -> None:
        self._counter = itertools.count()

    async def get_latest(self, tickers: list[str]) -> list[NewsEvent]:
        if not tickers:
            return []
        ticker = random.choice(tickers)
        return await self.get_for_ticker(ticker)

    async def get_for_ticker(self, ticker: str, max_items: int = 1) -> list[NewsEvent]:
        sequence = next(self._counter)
        templates = [
            ("raises guidance after stronger enterprise demand", "Management cited improving margins and stronger forward bookings."),
            ("faces margin pressure as input costs rise", "Analysts expect near-term volatility while cost controls are evaluated."),
            ("announces new AI product partnership", "The deal may expand revenue channels over the next two quarters."),
            ("reports mixed earnings with cautious outlook", "Revenue beat expectations, but guidance landed below consensus."),
        ]
        headline_tail, body = random.choice(templates)
        return [
            NewsEvent(
                ticker=ticker,
                headline=f"{ticker} {headline_tail}",
                body=f"{body} Event sequence {sequence}.",
            )
        ]


class YFinanceNewsProvider(NewsProvider):
    def __init__(self, fallback: NewsProvider | None = None) -> None:
        self.fallback = fallback or MockNewsProvider()
        self._seen_links: set[str] = set()

    async def get_latest(self, tickers: list[str]) -> list[NewsEvent]:
        events: list[NewsEvent] = []
        for ticker in tickers:
            events.extend(await self.get_for_ticker(ticker, max_items=1))
        return events

    async def get_for_ticker(self, ticker: str, max_items: int = 1) -> list[NewsEvent]:
        import asyncio

        try:
            events = await asyncio.to_thread(self._get_for_ticker_sync, ticker, max_items)
        except Exception:
            events = []
        return events or await self.fallback.get_for_ticker(ticker, max_items=max_items)

    def _get_for_ticker_sync(self, ticker: str, max_items: int) -> list[NewsEvent]:
        import yfinance as yf

        raw_news = yf.Ticker(ticker).get_news()
        events: list[NewsEvent] = []
        for item in raw_news:
            event = self._parse_news_item(ticker, item)
            if not event or (event.url and event.url in self._seen_links):
                continue
            if not is_ticker_relevant_event(event):
                continue
            if event.url:
                self._seen_links.add(event.url)
            events.append(event)
            if len(events) >= max_items:
                break
        return events

    def _parse_news_item(self, ticker: str, item: dict) -> NewsEvent | None:
        content = item.get("content") if isinstance(item.get("content"), dict) else item
        headline = clean_news_text(
            str(content.get("title") or content.get("headline") or ""))
        summary = clean_news_text(
            str(content.get("summary") or content.get("description") or headline))
        if not headline:
            return None

        url_value = content.get("canonicalUrl") or content.get("clickThroughUrl") or content.get("link")
        if isinstance(url_value, dict):
            url = url_value.get("url")
        else:
            url = url_value

        published = content.get("pubDate") or content.get("displayTime") or item.get("providerPublishTime")
        published_at = parse_yfinance_datetime(published)
        publisher = content.get("provider", {}).get("displayName") if isinstance(content.get("provider"), dict) else None
        return NewsEvent(
            ticker=ticker,
            headline=headline,
            body=summary,
            source=f"yfinance:{publisher or 'Yahoo Finance'}",
            url=url,
            published_at=published_at,
        )


class FinnhubNewsProvider(NewsProvider):
    def __init__(self, settings: Settings, fallback: NewsProvider | None = None) -> None:
        self.settings = settings
        self.fallback = fallback or MockNewsProvider()
        self._cursor = 0
        self._seen_ids: set[str] = set()
        self._last_request_at: datetime | None = None
        self._lock = None
        self._bootstrap_complete = False

    def mark_bootstrap_complete(self) -> None:
        self._bootstrap_complete = True

    async def get_for_ticker(self, ticker: str, max_items: int = 1) -> list[NewsEvent]:
        if self.settings.finnhub_api_key and is_finnhub_company_symbol(ticker):
            events = await self._fetch_company_news(ticker, max_items=max_items)
            if events:
                return events
        return await self.fallback.get_for_ticker(ticker, max_items=max_items)

    async def get_latest(self, tickers: list[str]) -> list[NewsEvent]:
        if not self.settings.finnhub_api_key:
            return await self.fallback.get_latest(tickers)

        is_bootstrap = self.settings.finnhub_news_bootstrap_on_start and not self._bootstrap_complete
        selected = self._bootstrap_symbols(tickers) if is_bootstrap else self._next_symbols(
            [ticker for ticker in tickers if is_finnhub_company_symbol(ticker)]
        )
        if not selected:
            return await self.fallback.get_latest(tickers)
        per_symbol_limit = (
            self.settings.finnhub_news_bootstrap_events_per_symbol
            if is_bootstrap
            else self.settings.finnhub_news_max_events_per_poll
        )
        total_limit = (
            max(1, len(selected) * max(1, per_symbol_limit))
            if is_bootstrap
            else self.settings.finnhub_news_max_events_per_poll
        )
        events: list[NewsEvent] = []
        for symbol in selected:
            if is_finnhub_company_symbol(symbol):
                symbol_events = await self._fetch_company_news(symbol, max_items=per_symbol_limit)
                if symbol_events is None:
                    symbol_events = await self.fallback.get_for_ticker(symbol, max_items=per_symbol_limit)
                elif not symbol_events and is_bootstrap:
                    symbol_events = await self.fallback.get_for_ticker(symbol, max_items=per_symbol_limit)
            else:
                symbol_events = await self.fallback.get_for_ticker(symbol, max_items=per_symbol_limit)
            events.extend(symbol_events)
            if len(events) >= total_limit:
                break
        if is_bootstrap:
            self._bootstrap_complete = True

        return events[:total_limit]

    async def bootstrap_for_tickers(self, tickers: list[str], max_items_per_ticker: int = 1) -> list[NewsEvent]:
        selected = self._bootstrap_symbols(tickers)
        events: list[NewsEvent] = []
        for ticker in selected:
            events.extend(await self.get_for_ticker(ticker, max_items=max_items_per_ticker))
        self._bootstrap_complete = True
        return events

    def _next_symbols(self, symbols: list[str]) -> list[str]:
        count = max(1, min(self.settings.finnhub_news_symbols_per_poll, len(symbols)))
        selected = [symbols[(self._cursor + offset) % len(symbols)] for offset in range(count)]
        self._cursor = (self._cursor + count) % len(symbols)
        return selected

    def _bootstrap_symbols(self, symbols: list[str]) -> list[str]:
        limit = max(1, min(self.settings.finnhub_news_bootstrap_symbol_limit, len(symbols)))
        selected = symbols[:limit]
        self._cursor = limit % len(symbols)
        return selected

    async def _fetch_company_news(self, symbol: str, max_items: int) -> list[NewsEvent] | None:
        await self._wait_for_rate_limit()
        today = datetime.now(UTC).date()
        start = today - timedelta(days=max(1, self.settings.finnhub_news_lookback_days))
        params = {
            "symbol": symbol,
            "from": start.isoformat(),
            "to": today.isoformat(),
            "token": self.settings.finnhub_api_key,
        }
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                response = await client.get("https://finnhub.io/api/v1/company-news", params=params)
                response.raise_for_status()
                payload = response.json()
        except Exception:
            return None

        if not isinstance(payload, list):
            return []

        events: list[NewsEvent] = []
        for item in sorted(payload, key=lambda row: row.get("datetime", 0), reverse=True):
            event_id = str(item.get("id") or "")
            headline = clean_news_text(str(item.get("headline") or ""))
            summary = clean_news_text(str(item.get("summary") or ""))
            if not event_id or event_id in self._seen_ids or not headline:
                continue
            event = NewsEvent(
                ticker=symbol,
                headline=headline,
                body=summary or headline,
                source=f"finnhub:{item.get('source') or 'company-news'}",
                url=item.get("url"),
                published_at=datetime.fromtimestamp(int(item.get("datetime") or 0), tz=UTC),
            )
            if not is_ticker_relevant_event(event):
                continue
            self._seen_ids.add(event_id)
            events.append(event)
            if len(events) >= max_items:
                break
        return events

    async def _wait_for_rate_limit(self) -> None:
        import asyncio

        if self._lock is None:
            self._lock = asyncio.Lock()

        async with self._lock:
            now = datetime.now(UTC)
            per_minute_interval = 60 / max(1, self.settings.finnhub_rate_limit_per_minute)
            per_second_interval = 1 / max(1, self.settings.finnhub_max_calls_per_second)
            minimum_interval = max(per_minute_interval, per_second_interval, 1.1)
            if self._last_request_at is not None:
                elapsed = (now - self._last_request_at).total_seconds()
                if elapsed < minimum_interval:
                    await asyncio.sleep(minimum_interval - elapsed)
            self._last_request_at = datetime.now(UTC)


def is_finnhub_company_symbol(ticker: str) -> bool:
    return bool(re.fullmatch(r"[A-Z]{1,5}(\.[A-Z])?", ticker))


def clean_news_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    cleaned = "".join(
        char
        if unicodedata.category(char)[0] != "C" or char in {"\n", "\t", " "}
        else " "
        for char in normalized
    )
    return " ".join(cleaned.split()).strip()


def is_ticker_relevant_event(event: NewsEvent) -> bool:
    text = f"{event.headline} {event.body}".lower()
    aliases = ticker_aliases(event.ticker)
    for alias in aliases:
        escaped = re.escape(alias.lower())
        if re.search(rf"(?<![a-z0-9])\$?{escaped}(?![a-z0-9])", text):
            return True
    return False


def ticker_aliases(ticker: str) -> tuple[str, ...]:
    normalized = ticker.upper()
    if normalized in TICKER_ALIASES:
        return TICKER_ALIASES[normalized]
    base_symbol = normalized.split("-")[0].split(".")[0]
    return (normalized.lower(), base_symbol.lower())


def parse_yfinance_datetime(value: object) -> datetime:
    if isinstance(value, int | float):
        return datetime.fromtimestamp(value, tz=UTC)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now(UTC)
