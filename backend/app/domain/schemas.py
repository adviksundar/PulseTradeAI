from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SentimentLabel(StrEnum):
    bullish = "Bullish"
    neutral = "Neutral"
    bearish = "Bearish"


class RiskLevel(StrEnum):
    low = "Low"
    medium = "Medium"
    high = "High"


class MarketTick(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    ticker: str
    price: float
    previous_price: float
    volume: int
    previous_volume: int
    source: str = "mock"
    timestamp: datetime = Field(default_factory=utc_now)

    @property
    def change_pct(self) -> float:
        if self.previous_price == 0:
            return 0.0
        return ((self.price - self.previous_price) / self.previous_price) * 100


class MarketHistoryPoint(BaseModel):
    ticker: str
    price: float
    volume: int
    timestamp: datetime


class MarketHistory(BaseModel):
    ticker: str
    range: str
    source: str
    points: list[MarketHistoryPoint]


class NewsEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    ticker: str
    headline: str
    body: str
    source: str = "mock-news"
    url: str | None = None
    published_at: datetime = Field(default_factory=utc_now)


class AIInsight(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    ticker: str
    summary: str
    key_events: list[str] = Field(default_factory=list)
    sentiment: SentimentLabel
    sentiment_score: float = Field(ge=-1, le=1)
    confidence: float = Field(ge=0, le=1)
    sentiment_source: str | None = None
    raw_sentiment_score: float | None = None
    risk_level: RiskLevel
    market_impact: str
    source_event_id: str
    created_at: datetime = Field(default_factory=utc_now)


class AlertType(StrEnum):
    price_move = "price_move"
    volume_spike = "volume_spike"
    sentiment_shift = "sentiment_shift"
    breaking_news = "breaking_news"


class Alert(BaseModel):
    alert_id: str = Field(default_factory=lambda: str(uuid4()))
    ticker: str
    alert_type: AlertType
    title: str
    message: str
    severity: RiskLevel
    confidence: float = Field(ge=0, le=1)
    created_at: datetime = Field(default_factory=utc_now)
    related_event_id: str | None = None


class DashboardSnapshot(BaseModel):
    ticks: list[MarketTick]
    insights: list[AIInsight]
    alerts: list[Alert]


class Watchlist(BaseModel):
    tickers: list[str]
    rejected: list[str] = Field(default_factory=list)


class WatchlistUpdate(BaseModel):
    tickers: list[str] = Field(min_length=1)
