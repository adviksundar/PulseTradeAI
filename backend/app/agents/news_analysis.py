from app.domain.schemas import AIInsight, NewsEvent, RiskLevel, SentimentLabel


class NewsAnalysisAgent:
    async def analyze(self, event: NewsEvent) -> AIInsight:
        text = f"{event.headline} {event.body}".lower()
        bearish_terms = ["pressure", "cautious", "weaker", "below", "costs", "risk"]
        bullish_terms = ["raises", "stronger", "partnership", "improving", "beat", "expand"]
        score = sum(term in text for term in bullish_terms) - sum(term in text for term in bearish_terms)

        if score > 0:
            sentiment = SentimentLabel.bullish
            sentiment_score = min(0.85, 0.25 + score * 0.2)
            risk = RiskLevel.medium
        elif score < 0:
            sentiment = SentimentLabel.bearish
            sentiment_score = max(-0.85, -0.25 + score * 0.2)
            risk = RiskLevel.high
        else:
            sentiment = SentimentLabel.neutral
            sentiment_score = 0.0
            risk = RiskLevel.low

        return AIInsight(
            ticker=event.ticker,
            summary=event.headline,
            key_events=[event.headline],
            sentiment=sentiment,
            sentiment_score=sentiment_score,
            confidence=0.78,
            risk_level=risk,
            market_impact="Monitor price and volume reaction over the next trading window.",
            source_event_id=event.event_id,
        )

