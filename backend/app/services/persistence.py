import logging
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    MetaData,
    String,
    Table,
    Text,
    delete,
    insert,
    select,
    text,
    update,
)
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.config import Settings
from app.domain.schemas import AIInsight, Alert, MarketTick, NewsEvent, utc_now

logger = logging.getLogger(__name__)
metadata = MetaData()


market_ticks = Table(
    "market_ticks",
    metadata,
    Column("event_id", String(64), primary_key=True),
    Column("ticker", String(32), index=True),
    Column("price", Float),
    Column("previous_price", Float),
    Column("volume", BigInteger),
    Column("previous_volume", BigInteger),
    Column("change_pct", Float),
    Column("source", String(80)),
    Column("timestamp", DateTime(timezone=True), index=True),
    Column("payload", JSON),
)

news_events = Table(
    "news_events",
    metadata,
    Column("event_id", String(64), primary_key=True),
    Column("ticker", String(32), index=True),
    Column("headline", Text),
    Column("body", Text),
    Column("source", String(120)),
    Column("url", Text),
    Column("published_at", DateTime(timezone=True), index=True),
    Column("payload", JSON),
)

ai_insights = Table(
    "ai_insights",
    metadata,
    Column("event_id", String(64), primary_key=True),
    Column("source_event_id", String(64), index=True),
    Column("ticker", String(32), index=True),
    Column("summary", Text),
    Column("sentiment", String(24)),
    Column("sentiment_score", Float),
    Column("confidence", Float),
    Column("risk_level", String(24)),
    Column("sentiment_source", String(80)),
    Column("raw_sentiment_score", Float),
    Column("created_at", DateTime(timezone=True), index=True),
    Column("payload", JSON),
)

alerts = Table(
    "alerts",
    metadata,
    Column("alert_id", String(64), primary_key=True),
    Column("ticker", String(32), index=True),
    Column("alert_type", String(40)),
    Column("severity", String(24)),
    Column("confidence", Float),
    Column("title", Text),
    Column("message", Text),
    Column("related_event_id", String(64), index=True),
    Column("created_at", DateTime(timezone=True), index=True),
    Column("payload", JSON),
)

watchlist_symbols = Table(
    "watchlist_symbols",
    metadata,
    Column("ticker", String(32), primary_key=True),
    Column("active", Boolean, nullable=False, default=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)


class EventStore:
    """PostgreSQL persistence with a silent disabled mode for local demos."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.engine: AsyncEngine | None = None
        self.connected = False
        self.last_error: str | None = None

    async def connect(self) -> None:
        try:
            self.engine = create_async_engine(self.settings.database_url, pool_pre_ping=True)
            async with self.engine.begin() as conn:
                await conn.run_sync(metadata.create_all)
                await conn.execute(
                    text(
                        "ALTER TABLE market_ticks "
                        "ALTER COLUMN volume TYPE BIGINT, "
                        "ALTER COLUMN previous_volume TYPE BIGINT"
                    )
                )
            self.connected = True
            self.last_error = None
        except Exception as exc:
            self.connected = False
            self.last_error = str(exc)[:240]
            logger.warning("postgres_unavailable persistence_disabled error=%s", self.last_error)
            if self.engine:
                await self.engine.dispose()
            self.engine = None

    async def close(self) -> None:
        if self.engine:
            await self.engine.dispose()

    def status(self) -> dict[str, object]:
        return {
            "backend": "postgres",
            "connected": self.connected,
            "url": mask_connection_url(self.settings.database_url),
            "last_error": self.last_error,
        }

    async def save_market_tick(self, tick: MarketTick) -> None:
        await self._execute(
            insert(market_ticks).values(
                event_id=tick.event_id,
                ticker=tick.ticker,
                price=tick.price,
                previous_price=tick.previous_price,
                volume=tick.volume,
                previous_volume=tick.previous_volume,
                change_pct=tick.change_pct,
                source=tick.source,
                timestamp=tick.timestamp,
                payload=tick.model_dump(mode="json"),
            )
        )

    async def save_news_event(self, event: NewsEvent) -> None:
        await self._execute(
            insert(news_events).values(
                event_id=event.event_id,
                ticker=event.ticker,
                headline=event.headline,
                body=event.body,
                source=event.source,
                url=event.url,
                published_at=event.published_at,
                payload=event.model_dump(mode="json"),
            )
        )

    async def save_insight(self, insight: AIInsight) -> None:
        await self._execute(
            insert(ai_insights).values(
                event_id=insight.event_id,
                source_event_id=insight.source_event_id,
                ticker=insight.ticker,
                summary=insight.summary,
                sentiment=insight.sentiment.value,
                sentiment_score=insight.sentiment_score,
                confidence=insight.confidence,
                risk_level=insight.risk_level.value,
                sentiment_source=insight.sentiment_source,
                raw_sentiment_score=insight.raw_sentiment_score,
                created_at=insight.created_at,
                payload=insight.model_dump(mode="json"),
            )
        )

    async def save_alert(self, alert: Alert) -> None:
        await self._execute(
            insert(alerts).values(
                alert_id=alert.alert_id,
                ticker=alert.ticker,
                alert_type=alert.alert_type.value,
                severity=alert.severity.value,
                confidence=alert.confidence,
                title=alert.title,
                message=alert.message,
                related_event_id=alert.related_event_id,
                created_at=alert.created_at,
                payload=alert.model_dump(mode="json"),
            )
        )

    async def load_watchlist(self, fallback: list[str]) -> list[str]:
        if not self.engine or not self.connected:
            return list(fallback)
        try:
            async with self.engine.begin() as conn:
                rows = await conn.execute(
                    select(watchlist_symbols.c.ticker)
                    .where(watchlist_symbols.c.active.is_(True))
                    .order_by(watchlist_symbols.c.created_at)
                )
                tickers = [str(row[0]) for row in rows]
                if tickers:
                    return tickers
                await self._seed_watchlist(conn, fallback)
                return list(fallback)
        except Exception as exc:
            self.last_error = str(exc)[:240]
            logger.warning("postgres_watchlist_load_failed error=%s", self.last_error)
            return list(fallback)

    async def add_watchlist_symbols(self, tickers: list[str]) -> None:
        if not self.engine or not self.connected or not tickers:
            return
        now = utc_now()
        try:
            async with self.engine.begin() as conn:
                for ticker in tickers:
                    await conn.execute(
                        text(
                            """
                            INSERT INTO watchlist_symbols (ticker, active, created_at, updated_at)
                            VALUES (:ticker, true, :now, :now)
                            ON CONFLICT (ticker)
                            DO UPDATE SET active = true, updated_at = EXCLUDED.updated_at
                            """
                        ),
                        {"ticker": ticker, "now": now},
                    )
        except Exception as exc:
            self.last_error = str(exc)[:240]
            logger.warning("postgres_watchlist_add_failed error=%s", self.last_error)

    async def remove_watchlist_symbol(self, ticker: str) -> None:
        if not self.engine or not self.connected:
            return
        try:
            async with self.engine.begin() as conn:
                await conn.execute(
                    update(watchlist_symbols)
                    .where(watchlist_symbols.c.ticker == ticker)
                    .values(active=False, updated_at=utc_now())
                )
        except Exception as exc:
            self.last_error = str(exc)[:240]
            logger.warning("postgres_watchlist_remove_failed error=%s", self.last_error)

    async def replace_watchlist(self, tickers: list[str]) -> None:
        if not self.engine or not self.connected:
            return
        try:
            async with self.engine.begin() as conn:
                await conn.execute(delete(watchlist_symbols))
                await self._seed_watchlist(conn, tickers)
        except Exception as exc:
            self.last_error = str(exc)[:240]
            logger.warning("postgres_watchlist_replace_failed error=%s", self.last_error)

    async def _execute(self, statement: Any) -> None:
        if not self.engine or not self.connected:
            return
        try:
            async with self.engine.begin() as conn:
                await conn.execute(statement)
        except Exception as exc:
            self.last_error = str(exc)[:240]
            logger.warning("postgres_write_failed error=%s", self.last_error)

    async def _seed_watchlist(self, conn: Any, tickers: list[str]) -> None:
        now = utc_now()
        for ticker in tickers:
            await conn.execute(
                insert(watchlist_symbols).values(
                    ticker=ticker,
                    active=True,
                    created_at=now,
                    updated_at=now,
                )
            )


def mask_connection_url(url: str) -> str:
    try:
        parts = urlsplit(url)
        if "@" not in parts.netloc:
            return url
        userinfo, hostinfo = parts.netloc.rsplit("@", 1)
        username = userinfo.split(":", 1)[0]
        masked = f"{username}:***@{hostinfo}" if username else f"***@{hostinfo}"
        return urlunsplit((parts.scheme, masked, parts.path, parts.query, parts.fragment))
    except Exception:
        return "<configured>"
