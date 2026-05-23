from app.core.config import Settings
from app.domain.schemas import AIInsight, Alert, AlertType, MarketTick, RiskLevel, SentimentLabel


class AlertDecisionAgent:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._last_sentiment: dict[str, SentimentLabel] = {}
        self._active_price_alerts: set[tuple[str, str]] = set()
        self._active_volume_alerts: set[str] = set()

    async def from_tick(self, tick: MarketTick) -> list[Alert]:
        alerts: list[Alert] = []
        direction = "up" if tick.change_pct > 0 else "down"
        price_key = (tick.ticker, direction)
        if abs(tick.change_pct) < self.settings.price_alert_threshold_pct:
            self._active_price_alerts.discard((tick.ticker, "up"))
            self._active_price_alerts.discard((tick.ticker, "down"))
        elif price_key not in self._active_price_alerts:
            self._active_price_alerts.add(price_key)
            alerts.append(
                Alert(
                    ticker=tick.ticker,
                    alert_type=AlertType.price_move,
                    title=f"{tick.ticker} price moved {direction}",
                    message=f"{tick.ticker} moved {tick.change_pct:.2f}% to {tick.price:.2f}.",
                    severity=RiskLevel.medium,
                    confidence=0.82,
                    related_event_id=tick.event_id,
                )
            )

        volume_ratio = tick.volume / tick.previous_volume if tick.previous_volume else 0
        if volume_ratio < self.settings.volume_alert_multiplier:
            self._active_volume_alerts.discard(tick.ticker)
        elif tick.ticker not in self._active_volume_alerts:
            self._active_volume_alerts.add(tick.ticker)
            alerts.append(
                Alert(
                    ticker=tick.ticker,
                    alert_type=AlertType.volume_spike,
                    title=f"{tick.ticker} volume spike",
                    message=f"Volume jumped to {tick.volume:,}, above recent baseline.",
                    severity=RiskLevel.medium,
                    confidence=0.75,
                    related_event_id=tick.event_id,
                )
            )
        return alerts

    async def from_insight(self, insight: AIInsight) -> list[Alert]:
        previous = self._last_sentiment.get(insight.ticker)
        self._last_sentiment[insight.ticker] = insight.sentiment
        alerts = [
            Alert(
                ticker=insight.ticker,
                alert_type=AlertType.breaking_news,
                title=f"{insight.ticker} news analyzed",
                message=f"{insight.sentiment} sentiment: {insight.summary}",
                severity=insight.risk_level,
                confidence=insight.confidence,
                related_event_id=insight.event_id,
            )
        ]
        if previous and previous != insight.sentiment:
            alerts.append(
                Alert(
                    ticker=insight.ticker,
                    alert_type=AlertType.sentiment_shift,
                    title=f"{insight.ticker} sentiment shifted",
                    message=f"Sentiment moved from {previous} to {insight.sentiment}.",
                    severity=RiskLevel.high,
                    confidence=insight.confidence,
                    related_event_id=insight.event_id,
                )
            )
        return alerts
