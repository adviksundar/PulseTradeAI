from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.schemas import AlertType, NewsEvent, RiskLevel, SentimentLabel, utc_now


class AgentName(StrEnum):
    news_analysis = "news_analysis"
    sentiment = "sentiment"
    risk = "risk"
    alert_decision = "alert_decision"
    market_brief = "market_brief"


class StrictAgentOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NewsAnalysisOutput(StrictAgentOutput):
    summary: str = Field(max_length=280)
    key_event: str = Field(max_length=140)
    affected_company: str = Field(max_length=120)
    market_impact_summary: str = Field(max_length=180)
    extracted_keywords: list[str] = Field(max_length=8)


class SentimentOutput(StrictAgentOutput):
    sentiment_label: SentimentLabel
    confidence_score: float = Field(ge=0, le=1)
    # Optional raw score and source for auditing (e.g., 'finbert' or 'lexicon')
    raw_score: float | None = None
    source: str | None = None
    reasoning: str = Field(max_length=180)


class RiskOutput(StrictAgentOutput):
    risk_level: RiskLevel
    anomaly_score: float = Field(ge=0, le=1)
    volatility_summary: str = Field(max_length=180)
    reasoning: str = Field(max_length=180)


class AlertDecisionOutput(StrictAgentOutput):
    should_alert: bool
    alert_priority: Literal["low", "medium", "high"]
    alert_title: str = Field(max_length=96)
    alert_message: str = Field(max_length=220)
    urgency_level: RiskLevel


class MarketBriefOutput(StrictAgentOutput):
    short_market_brief: str = Field(max_length=280)
    market_outlook: Literal["bullish", "neutral", "bearish"]
    trader_style_insight_summary: str = Field(max_length=180)


class AgentTrace(BaseModel):
    agent: AgentName
    model: str
    status: Literal["ok", "fallback", "error"]
    calls_made: int = 0
    successful_calls: int = 0
    uses_openai: bool = False
    message: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class MarketContext(BaseModel):
    latest_price: float | None = None
    previous_price: float | None = None
    change_pct: float | None = None
    latest_volume: int | None = None
    previous_volume: int | None = None
    volume_ratio: float | None = None
    source: str | None = None


class FinancialEventState(BaseModel):
    event_id: str
    event_type: Literal["news"]
    ticker: str
    headline: str
    raw_text: str
    source: str
    url: str | None = None
    timestamp: datetime
    normalized_at: datetime = Field(default_factory=utc_now)
    market_context: MarketContext = Field(default_factory=MarketContext)
    news_analysis: NewsAnalysisOutput | None = None
    sentiment: SentimentOutput | None = None
    risk: RiskOutput | None = None
    alert_decision: AlertDecisionOutput | None = None
    market_brief: MarketBriefOutput | None = None
    trace: list[AgentTrace] = Field(default_factory=list)

    @classmethod
    def from_news_event(cls, event: NewsEvent, market_context: MarketContext | None = None) -> "FinancialEventState":
        return cls(
            event_id=event.event_id,
            event_type="news",
            ticker=event.ticker,
            headline=event.headline,
            raw_text=event.body,
            source=event.source,
            url=event.url,
            timestamp=event.published_at,
            market_context=market_context or MarketContext(),
        )


def alert_type_from_priority(priority: str) -> AlertType:
    return AlertType.breaking_news if priority in {"medium", "high"} else AlertType.sentiment_shift
