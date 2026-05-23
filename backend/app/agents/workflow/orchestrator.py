import logging

from app.agents.workflow.agents import (
    AlertDecisionWorkflowAgent,
    MarketBriefWorkflowAgent,
    NewsAnalysisWorkflowAgent,
    RiskScoringWorkflowAgent,
    SentimentAnalysisWorkflowAgent,
)
from app.agents.workflow.llm_client import StructuredOpenAIClient
from app.agents.workflow.state import AgentName, AgentTrace, FinancialEventState, MarketContext
from app.core.config import Settings
from app.domain.schemas import AIInsight, Alert, AlertType, MarketTick, NewsEvent

logger = logging.getLogger(__name__)


class FinancialIntelligenceOrchestrator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = StructuredOpenAIClient(settings)
        self.news_agent = NewsAnalysisWorkflowAgent(self.client, settings)
        self.sentiment_agent = SentimentAnalysisWorkflowAgent(
            self.client, settings)
        self.risk_agent = RiskScoringWorkflowAgent(self.client, settings)
        self.alert_agent = AlertDecisionWorkflowAgent(self.client, settings)
        self.brief_agent = MarketBriefWorkflowAgent(self.client, settings)
        self.state_history: list[FinancialEventState] = []
        self.workflow_logs: list[dict[str, object]] = []
        self.stage_call_counts: dict[str, int] = {
            AgentName.news_analysis.value: 0,
            AgentName.sentiment.value: 0,
            AgentName.risk.value: 0,
            AgentName.alert_decision.value: 0,
            AgentName.market_brief.value: 0,
        }
        self.stage_success_counts: dict[str, int] = {
            AgentName.news_analysis.value: 0,
            AgentName.sentiment.value: 0,
            AgentName.risk.value: 0,
            AgentName.alert_decision.value: 0,
            AgentName.market_brief.value: 0,
        }

    async def process_news_event(
        self,
        event: NewsEvent,
        latest_tick: MarketTick | None = None,
    ) -> tuple[FinancialEventState, AIInsight, Alert | None]:
        state = FinancialEventState.from_news_event(
            event, market_context=market_context_from_tick(latest_tick))

        state.news_analysis = await self.news_agent.run(state)
        self._trace(state, AgentName.news_analysis,
                    self.settings.openai_fast_model, uses_openai=True)

        state.sentiment = await self.sentiment_agent.run(state)
        self._trace(state, AgentName.sentiment,
                    self.settings.openai_fast_model, uses_openai=False)

        state.risk = await self.risk_agent.run(state)
        self._trace(state, AgentName.risk,
                    self.settings.openai_fast_model, uses_openai=False)

        state.alert_decision = await self.alert_agent.run(state)
        self._trace(state, AgentName.alert_decision,
                    self.settings.openai_fast_model, uses_openai=False)

        state.market_brief = await self.brief_agent.run(state)
        self._trace(state, AgentName.market_brief,
                    self.settings.openai_brief_model, uses_openai=True)

        self.state_history = [state, *self.state_history[:49]]
        # detect and log rapid high-confidence flips for the same ticker
        prev = next(
            (s for s in self.state_history[1:] if s.ticker == state.ticker), None)
        try:
            if prev and prev.sentiment and state.sentiment:
                prev_label = prev.sentiment.sentiment_label
                new_label = state.sentiment.sentiment_label
                prev_conf = prev.sentiment.confidence_score
                new_conf = state.sentiment.confidence_score
                if prev_label != new_label and new_conf >= 0.9 and prev_conf >= 0.6:
                    logger.warning(
                        "high_confidence_flip",
                        extra={
                            "ticker": state.ticker,
                            "prev_label": prev_label.value,
                            "prev_conf": prev_conf,
                            "prev_source": prev.sentiment.source,
                            "prev_raw": prev.sentiment.raw_score,
                            "new_label": new_label.value,
                            "new_conf": new_conf,
                            "new_source": state.sentiment.source,
                            "new_raw": state.sentiment.raw_score,
                            "event_id": state.event_id,
                        },
                    )
        except Exception:
            pass
        logger.info("agent_workflow_complete", extra={
                    "ticker": state.ticker, "event_id": state.event_id})
        return state, state_to_ai_insight(state), state_to_alert(state)

    def _trace(self, state: FinancialEventState, agent: AgentName, model: str, uses_openai: bool) -> None:
        status = self.client.last_status if self.client.last_status in {
            "ok", "fallback", "error"} else "fallback"
        calls_made = self.client.last_call_count if uses_openai else 0
        successful_calls = self.client.last_success_count if uses_openai else 0
        self.stage_call_counts[agent.value] += calls_made
        self.stage_success_counts[agent.value] += successful_calls
        trace = AgentTrace(
            agent=agent,
            model=model,
            status=status,
            calls_made=calls_made,
            successful_calls=successful_calls,
            uses_openai=uses_openai,
            message=self.client.last_error_message,
        )
        state.trace.append(trace)
        self.workflow_logs = [
            {
                "event_id": state.event_id,
                "ticker": state.ticker,
                "headline": state.headline,
                "agent": trace.agent.value,
                "status": trace.status,
                "model": trace.model,
                "uses_openai": trace.uses_openai,
                "calls_made": trace.calls_made,
                "successful_calls": trace.successful_calls,
                "message": trace.message,
                "created_at": trace.created_at.isoformat(),
            },
            *self.workflow_logs[:99],
        ]


def market_context_from_tick(tick: MarketTick | None) -> MarketContext:
    if not tick:
        return MarketContext()
    volume_ratio = tick.volume / tick.previous_volume if tick.previous_volume else None
    return MarketContext(
        latest_price=tick.price,
        previous_price=tick.previous_price,
        change_pct=tick.change_pct,
        latest_volume=tick.volume,
        previous_volume=tick.previous_volume,
        volume_ratio=volume_ratio,
        source=tick.source,
    )


def state_to_ai_insight(state: FinancialEventState) -> AIInsight:
    assert state.news_analysis
    assert state.sentiment
    assert state.risk
    assert state.market_brief
    sentiment_score = {
        "Bullish": state.sentiment.confidence_score,
        "Neutral": 0.0,
        "Bearish": -state.sentiment.confidence_score,
    }[state.sentiment.sentiment_label.value]
    return AIInsight(
        ticker=state.ticker,
        summary=state.market_brief.short_market_brief,
        key_events=[state.news_analysis.key_event],
        sentiment=state.sentiment.sentiment_label,
        sentiment_score=sentiment_score,
        confidence=state.sentiment.confidence_score,
        sentiment_source=state.sentiment.source,
        raw_sentiment_score=state.sentiment.raw_score,
        risk_level=state.risk.risk_level,
        market_impact=state.news_analysis.market_impact_summary,
        source_event_id=state.event_id,
    )


def state_to_alert(state: FinancialEventState) -> Alert | None:
    if not state.alert_decision or not state.alert_decision.should_alert:
        return None
    return Alert(
        ticker=state.ticker,
        alert_type=AlertType.breaking_news,
        title=state.alert_decision.alert_title,
        message=state.alert_decision.alert_message,
        severity=state.alert_decision.urgency_level,
        confidence=state.sentiment.confidence_score if state.sentiment else 0.6,
        related_event_id=state.event_id,
    )
