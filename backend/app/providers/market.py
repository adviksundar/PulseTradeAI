import asyncio
import random
from datetime import timedelta
from typing import Any

from app.domain.schemas import MarketHistory, MarketHistoryPoint, MarketTick, utc_now


class MarketDataProvider:
    async def get_tick(self, ticker: str) -> MarketTick:
        raise NotImplementedError

    async def get_history(self, ticker: str, range_name: str) -> MarketHistory:
        raise NotImplementedError


class MockMarketDataProvider(MarketDataProvider):
    def __init__(self) -> None:
        self._state = {
            "AAPL": (188.0, 60_000_000),
            "MSFT": (424.0, 31_000_000),
            "NVDA": (920.0, 55_000_000),
            "TSLA": (175.0, 95_000_000),
            "BTC-USD": (68000.0, 500_000),
        }

    async def get_tick(self, ticker: str) -> MarketTick:
        price, volume = self._state.get(ticker, (100.0, 1_000_000))
        drift = random.uniform(-0.015, 0.015)
        shock = random.choice([0, 0, 0, random.uniform(-0.035, 0.035)])
        next_price = round(price * (1 + drift + shock), 2)
        next_volume = max(1, int(volume * random.uniform(0.85, 1.25)))
        self._state[ticker] = (next_price, next_volume)
        return MarketTick(
            ticker=ticker,
            price=next_price,
            previous_price=price,
            volume=next_volume,
            previous_volume=volume,
            source="mock-market",
        )

    async def get_history(self, ticker: str, range_name: str) -> MarketHistory:
        price, volume = self._state.get(ticker, (100.0, 1_000_000))
        count = history_point_count(range_name)
        step = history_step(range_name)
        now = utc_now()
        points: list[MarketHistoryPoint] = []
        current = price
        for index in range(count):
            age = count - index - 1
            current = max(1, current * (1 + random.uniform(-0.006, 0.006)))
            points.append(
                MarketHistoryPoint(
                    ticker=ticker,
                    price=round(current, 2),
                    volume=max(1, int(volume * random.uniform(0.75, 1.3))),
                    timestamp=now - (step * age),
                )
            )
        return MarketHistory(ticker=ticker, range=range_name, source="mock-market", points=points)


class YFinanceMarketDataProvider(MarketDataProvider):
    def __init__(self, fallback: MarketDataProvider | None = None) -> None:
        self.fallback = fallback or MockMarketDataProvider()
        self._previous: dict[str, tuple[float, int]] = {}

    async def get_tick(self, ticker: str) -> MarketTick:
        try:
            return await asyncio.to_thread(self._get_tick_sync, ticker)
        except Exception:
            return await self.fallback.get_tick(ticker)

    async def get_history(self, ticker: str, range_name: str) -> MarketHistory:
        try:
            return await asyncio.to_thread(self._get_history_sync, ticker, range_name)
        except Exception:
            return await self.fallback.get_history(ticker, range_name)

    def _get_tick_sync(self, ticker: str) -> MarketTick:
        import yfinance as yf

        yahoo_ticker = yf.Ticker(ticker)
        fast_info = yahoo_ticker.fast_info
        price = read_fast_info(fast_info, "last_price", "lastPrice")
        previous_close = read_fast_info(fast_info, "previous_close", "previousClose")
        volume = read_fast_info(fast_info, "last_volume", "lastVolume", "volume")

        if not price:
            history = yahoo_ticker.history(period="2d", interval="1d")
            if history.empty:
                raise ValueError(f"No yfinance quote data for {ticker}")
            price = float(history["Close"].iloc[-1])
            previous_close = float(history["Close"].iloc[-2]) if len(history) > 1 else price
            volume = int(history["Volume"].iloc[-1]) if "Volume" in history else 0

        current_price = round(float(price), 2)
        previous_price = round(float(previous_close or price), 2)
        _, previous_volume = self._previous.get(ticker, (previous_price, int(volume or 0)))
        current_volume = int(volume or previous_volume or 1)
        self._previous[ticker] = (current_price, current_volume)

        return MarketTick(
            ticker=ticker,
            price=current_price,
            previous_price=previous_price,
            volume=current_volume,
            previous_volume=previous_volume,
            source="yfinance",
        )

    def _get_history_sync(self, ticker: str, range_name: str) -> MarketHistory:
        import yfinance as yf

        period, interval = yfinance_history_window(range_name)
        history = yf.Ticker(ticker).history(period=period, interval=interval)
        if history.empty:
            raise ValueError(f"No yfinance history data for {ticker}")

        points = [
            MarketHistoryPoint(
                ticker=ticker,
                price=round(float(row["Close"]), 2),
                volume=int(row["Volume"] or 0),
                timestamp=index.to_pydatetime(),
            )
            for index, row in history.iterrows()
            if row.get("Close") is not None
        ]
        return MarketHistory(ticker=ticker, range=range_name, source="yfinance", points=points[-500:])


def read_fast_info(fast_info: Any, *keys: str) -> float | int | None:
    for key in keys:
        try:
            value = fast_info[key]
        except Exception:
            value = getattr(fast_info, key, None)
        if value is not None:
            return value
    return None


def yfinance_history_window(range_name: str) -> tuple[str, str]:
    return {
        "1D": ("1d", "5m"),
        "5D": ("5d", "15m"),
        "1M": ("1mo", "1h"),
        "3M": ("3mo", "1d"),
        "1Y": ("1y", "1d"),
        "5Y": ("5y", "1wk"),
        "Max": ("max", "1mo"),
    }.get(range_name, ("1d", "5m"))


def history_point_count(range_name: str) -> int:
    return {
        "1D": 78,
        "5D": 130,
        "1M": 160,
        "3M": 90,
        "1Y": 252,
        "5Y": 260,
        "Max": 360,
    }.get(range_name, 78)


def history_step(range_name: str) -> timedelta:
    return {
        "1D": timedelta(minutes=5),
        "5D": timedelta(minutes=15),
        "1M": timedelta(hours=1),
        "3M": timedelta(days=1),
        "1Y": timedelta(days=1),
        "5Y": timedelta(weeks=1),
        "Max": timedelta(days=30),
    }.get(range_name, timedelta(minutes=5))
