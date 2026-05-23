import asyncio
import json
import math
import threading

try:
    import tiktoken as _tiktoken  # type: ignore[import-not-found]
except Exception:
    _tiktoken = None

from app.agents.workflow.llm_client import StructuredOpenAIClient
from app.agents.workflow.state import (
    AlertDecisionOutput,
    FinancialEventState,
    MarketBriefOutput,
    NewsAnalysisOutput,
    RiskOutput,
    SentimentOutput,
)
from app.core.config import Settings
from app.domain.schemas import RiskLevel, SentimentLabel


BULLISH_PHRASES: dict[str, float] = {
    "price target raised": 2.6,
    "raises price target": 2.6,
    "strong buy": 2.4,
    "buy rating": 1.8,
    "raises guidance": 2.4,
    "raised guidance": 2.4,
    "beats expectations": 2.2,
    "beat expectations": 2.2,
    "revenue beat": 1.8,
    "earnings beat": 1.8,
    "margin expansion": 1.7,
    "strong demand": 1.7,
    "partnership": 1.2,
    "deal": 1.2,
    "upgrade": 1.8,
    "upgraded": 1.8,
    "record high": 1.5,
    "accelerating growth": 1.8,
}

BEARISH_PHRASES: dict[str, float] = {
    "price target cut": 2.6,
    "cuts price target": 2.6,
    "sell rating": 2.3,
    "downgrade": 2.0,
    "downgraded": 2.0,
    "lowers guidance": 2.4,
    "lowered guidance": 2.4,
    "misses expectations": 2.2,
    "missed expectations": 2.2,
    "revenue miss": 1.8,
    "earnings miss": 1.8,
    "margin pressure": 1.8,
    "cost pressure": 1.6,
    "regulatory probe": 2.0,
    "investigation": 1.8,
    "lawsuit": 1.7,
    "recall": 1.8,
    "layoffs": 1.4,
    "slowing demand": 1.8,
}

BULLISH_WORDS: dict[str, float] = {
    "beat": 1.1,
    "beats": 1.1,
    "raise": 1.0,
    "raises": 1.0,
    "raised": 1.0,
    "upgrade": 1.2,
    "upgraded": 1.2,
    "bullish": 1.2,
    "growth": 0.8,
    "surge": 1.1,
    "rally": 1.0,
    "gain": 0.7,
    "gains": 0.7,
    "strong": 0.8,
    "outperform": 1.0,
    "expansion": 0.8,
}

BEARISH_WORDS: dict[str, float] = {
    "miss": 1.1,
    "misses": 1.1,
    "cut": 1.1,
    "cuts": 1.1,
    "lower": 0.9,
    "lowered": 1.0,
    "downgrade": 1.2,
    "downgraded": 1.2,
    "bearish": 1.2,
    "risk": 0.7,
    "pressure": 0.8,
    "decline": 1.0,
    "falls": 1.0,
    "drop": 1.0,
    "weak": 0.9,
    "weaker": 1.0,
    "lawsuit": 1.2,
    "probe": 1.2,
    "recall": 1.1,
}

LOW_IMPACT_TERMS = [
    "personal finance",
    "mega backdoor roth",
    "etf fee",
    "how to",
    "opinion",
    "watchlist",
]

_FINBERT_PIPELINE = None
_FINBERT_LOCK = threading.Lock()


class NewsAnalysisWorkflowAgent:
    def __init__(self, client: StructuredOpenAIClient, settings: Settings) -> None:
        self.client = client
        self.model = settings.openai_fast_model

    async def run(self, state: FinancialEventState) -> NewsAnalysisOutput:
        article_excerpt = compact_text(state.raw_text, 900)
        try:
            return await self.client.generate_json(
                model=self.model,
                system_prompt=(
                    "You extract concise financial event facts. Return only schema-valid JSON. "
                    "Do not provide investment advice. Keep every field brief and dashboard-ready."
                ),
                user_payload={
                    "ticker": state.ticker,
                    "headline": state.headline,
                    "article_excerpt": article_excerpt,
                    "timestamp": state.timestamp,
                },
                output_model=NewsAnalysisOutput,
            )
        except Exception:
            return self.fallback(state)

    def fallback(self, state: FinancialEventState) -> NewsAnalysisOutput:
        text = f"{state.headline} {state.raw_text}".strip()
        keywords = [
            word.strip(".,:;()").lower()
            for word in text.split()
            if len(word.strip(".,:;()")) > 5
        ][:8]
        return NewsAnalysisOutput(
            summary=state.headline,
            key_event=state.headline,
            affected_company=state.ticker,
            market_impact_summary="Monitor price, volume, and sentiment reaction over the next refresh window.",
            extracted_keywords=keywords,
        )


class SentimentAnalysisWorkflowAgent:
    def __init__(self, client: StructuredOpenAIClient, settings: Settings) -> None:
        self.client = client
        self.model = settings.openai_fast_model
        self.settings = settings

    async def run(self, state: FinancialEventState) -> SentimentOutput:
        if self.settings.sentiment_provider == "finbert":
            try:
                output = await run_finbert_sentiment(state, self.settings.finbert_model)
                self.client.last_status = "ok"
                self.client.last_error_message = "FinBERT local transformer"
                return output
            except Exception as exc:
                self.client.last_status = "fallback"
                self.client.last_error_message = f"FinBERT unavailable; lexicon fallback: {exc}"
                return self.fallback(state)
        self.client.last_status = "fallback"
        self.client.last_error_message = "Finance lexicon sentiment classifier"
        return self.fallback(state)

    def fallback(self, state: FinancialEventState) -> SentimentOutput:
        raw_score, reasons = score_financial_sentiment(state)
        norm = normalize_lexicon_score(raw_score)
        # soften thresholds: require a moderate normalized signal to call bullish/bearish
        threshold = 0.25
        confidence = calibrate_confidence(norm)
        if norm >= threshold:
            return SentimentOutput(
                sentiment_label=SentimentLabel.bullish,
                confidence_score=min(0.95, confidence),
                raw_score=raw_score,
                source="lexicon",
                reasoning=truncate_reason(
                    "Bullish signals: " + ", ".join(reasons)),
            )
        if norm <= -threshold:
            return SentimentOutput(
                sentiment_label=SentimentLabel.bearish,
                confidence_score=min(0.95, confidence),
                raw_score=raw_score,
                source="lexicon",
                reasoning=truncate_reason(
                    "Bearish signals: " + ", ".join(reasons)),
            )
        # Neutral / weak signals
        neutral_conf = 0.52 if reasons else 0.5
        return SentimentOutput(
            sentiment_label=SentimentLabel.neutral,
            confidence_score=neutral_conf,
            raw_score=raw_score,
            source="lexicon",
            reasoning=truncate_reason(
                "Mixed or low-impact signal"
                + (f": {', '.join(reasons)}" if reasons else " with no clear financial catalyst")
            ),
        )


class RiskScoringWorkflowAgent:
    def __init__(self, client: StructuredOpenAIClient, settings: Settings) -> None:
        self.client = client
        self.model = settings.openai_fast_model

    async def run(self, state: FinancialEventState) -> RiskOutput:
        self.client.last_status = "fallback"
        self.client.last_error_message = "Deterministic risk scoring"
        return self.fallback(state)

    def fallback(self, state: FinancialEventState) -> RiskOutput:
        change = abs(state.market_context.change_pct or 0)
        volume_ratio = state.market_context.volume_ratio or 1
        sentiment = state.sentiment.sentiment_label if state.sentiment else SentimentLabel.neutral
        anomaly = min(1.0, (change / 8) + max(0, volume_ratio - 1) / 4)
        if anomaly >= 0.55 or sentiment == SentimentLabel.bearish:
            risk = RiskLevel.high
        elif anomaly >= 0.25 or sentiment != SentimentLabel.neutral:
            risk = RiskLevel.medium
        else:
            risk = RiskLevel.low
        return RiskOutput(
            risk_level=risk,
            anomaly_score=round(anomaly, 2),
            volatility_summary=f"{state.ticker} moved {change:.2f}% with volume ratio {volume_ratio:.2f}.",
            reasoning="Risk combines event sentiment with recent price and volume deviation.",
        )


class AlertDecisionWorkflowAgent:
    def __init__(self, client: StructuredOpenAIClient, settings: Settings) -> None:
        self.client = client
        self.model = settings.openai_fast_model

    async def run(self, state: FinancialEventState) -> AlertDecisionOutput:
        self.client.last_status = "fallback"
        self.client.last_error_message = "Deterministic alert decision"
        return self.fallback(state)

    def fallback(self, state: FinancialEventState) -> AlertDecisionOutput:
        risk = state.risk.risk_level if state.risk else RiskLevel.low
        sentiment = state.sentiment.sentiment_label if state.sentiment else SentimentLabel.neutral
        should_alert = risk != RiskLevel.low or sentiment != SentimentLabel.neutral
        priority = "high" if risk == RiskLevel.high else "medium" if should_alert else "low"
        return AlertDecisionOutput(
            should_alert=should_alert,
            alert_priority=priority,
            alert_title=f"{state.ticker} {sentiment.value.lower()} event detected",
            alert_message=f"{state.ticker} sentiment is {sentiment.value} after: {state.headline}",
            urgency_level=risk,
        )


class MarketBriefWorkflowAgent:
    def __init__(self, client: StructuredOpenAIClient, settings: Settings) -> None:
        self.client = client
        self.model = settings.openai_brief_model

    async def run(self, state: FinancialEventState) -> MarketBriefOutput:
        try:
            return await self.client.generate_json(
                model=self.model,
                system_prompt=(
                    "You write a short trader-style market intelligence brief. "
                    "Use plain language, avoid recommendations, and keep the brief under 45 words."
                ),
                user_payload=state.model_dump(mode="json", exclude={"trace"}),
                output_model=MarketBriefOutput,
            )
        except Exception:
            return self.fallback(state)

    def fallback(self, state: FinancialEventState) -> MarketBriefOutput:
        sentiment = state.sentiment.sentiment_label if state.sentiment else SentimentLabel.neutral
        outlook = {
            SentimentLabel.bullish: "bullish",
            SentimentLabel.bearish: "bearish",
            SentimentLabel.neutral: "neutral",
        }[sentiment]
        risk = state.risk.risk_level if state.risk else RiskLevel.low
        return MarketBriefOutput(
            short_market_brief=(
                f"{state.ticker} screens {sentiment.value.lower()} after {state.headline}. "
                f"Near-term risk is {risk.value.lower()}."
            ),
            market_outlook=outlook,
            trader_style_insight_summary="Watch follow-through in price and volume before treating the event as durable.",
        )


def score_financial_sentiment(state: FinancialEventState) -> tuple[float, list[str]]:
    analysis_text = ""
    if state.news_analysis:
        analysis_text = " ".join(
            [
                state.news_analysis.summary,
                state.news_analysis.key_event,
                state.news_analysis.market_impact_summary,
                " ".join(state.news_analysis.extracted_keywords),
            ]
        )
    text = f"{state.headline} {state.raw_text} {analysis_text}".lower()
    score = 0.0
    reasons: list[str] = []

    if any(term in text for term in LOW_IMPACT_TERMS):
        score -= 0.35 if score > 0 else 0
        reasons.append("low-impact context")

    for phrase, weight in BULLISH_PHRASES.items():
        if phrase in text:
            score += weight
            reasons.append(phrase)
    for phrase, weight in BEARISH_PHRASES.items():
        if phrase in text:
            score -= weight
            reasons.append(phrase)

    tokens = [token.strip(".,:;!?()[]{}\"'").lower() for token in text.split()]
    for index, token in enumerate(tokens):
        negated = any(word in tokens[max(0, index - 3): index]
                      for word in {"not", "no", "without"})
        if token in BULLISH_WORDS:
            score += -BULLISH_WORDS[token] * \
                0.7 if negated else BULLISH_WORDS[token]
            reasons.append(("not " if negated else "") + token)
        if token in BEARISH_WORDS:
            score += BEARISH_WORDS[token] * \
                0.7 if negated else -BEARISH_WORDS[token]
            reasons.append(("not " if negated else "") + token)

    market_change = state.market_context.change_pct or 0
    if abs(market_change) >= 1.0:
        score += 0.6 if market_change > 0 else -0.6
        reasons.append(f"market move {market_change:.2f}%")
    elif abs(market_change) >= 0.35:
        score += 0.25 if market_change > 0 else -0.25
        reasons.append(f"modest market move {market_change:.2f}%")

    unique_reasons = list(dict.fromkeys(reasons))
    return score, unique_reasons[:4]


def normalize_lexicon_score(raw_score: float, scale: float = 3.0) -> float:
    """Normalize an unbounded lexicon score into [-1, 1].

    Uses a soft compression (tanh) so extreme raw scores map smoothly to the
    unit interval. The `scale` parameter controls how quickly scores saturate
    (larger -> less saturation).
    """
    try:
        return math.tanh(raw_score / scale)
    except Exception:
        return 0.0


def compact_text(text: str, max_chars: int) -> str:
    """Trim whitespace and cap text length to reduce prompt bloat.

    If tiktoken is available, cap by token count first, then fall back to a
    character cap. This keeps prompts smaller and more predictable.
    """
    cleaned = " ".join(text.split())
    token_limited = truncate_by_tokens(cleaned, max_tokens=220)
    return token_limited[:max_chars]


def truncate_by_tokens(text: str, max_tokens: int) -> str:
    if not text:
        return text
    if _tiktoken is None:
        return text
    try:
        encoding = _tiktoken.get_encoding("cl100k_base")
        tokens = encoding.encode(text)
        if len(tokens) <= max_tokens:
            return text
        return encoding.decode(tokens[:max_tokens])
    except Exception:
        return text


def calibrate_confidence(norm_score: float, min_conf: float = 0.5, max_conf: float = 0.95) -> float:
    """Map a normalized score in [-1,1] to a confidence in [min_conf, max_conf].

    This produces conservative confidences near 0 and higher confidence as the
    absolute signal strengthens.
    """
    magnitude = min(1.0, max(0.0, abs(norm_score)))
    return min(max_conf, min_conf + (max_conf - min_conf) * magnitude)


async def run_finbert_sentiment(state: FinancialEventState, model_name: str) -> SentimentOutput:
    result = await asyncio.to_thread(classify_with_finbert, finbert_text(state), model_name)
    label = normalize_finbert_label(str(result["label"]))
    # `result` now contains `label` and `score` where `score` is a probability-like
    # confidence in [0, 1]. Map that into our `SentimentOutput` confidence range.
    raw_score = float(result.get("score", 0.0))
    score = raw_score
    sentiment = {
        "positive": SentimentLabel.bullish,
        "negative": SentimentLabel.bearish,
        "neutral": SentimentLabel.neutral,
    }[label]
    confidence = max(0.5, min(0.95, score))
    return SentimentOutput(
        sentiment_label=sentiment,
        confidence_score=confidence,
        raw_score=raw_score,
        source="finbert",
        reasoning=f"FinBERT classified financial tone as {label} with {confidence:.0%} confidence.",
    )


def classify_with_finbert(text: str, model_name: str) -> dict[str, object]:
    """Thread-safe FinBERT classification.

    Returns a dict with keys `label` and `score` where `score` is a
    probability-like confidence in [0, 1]. Uses a lock to avoid init races
    and detects CUDA if available to set the pipeline device.
    """
    global _FINBERT_PIPELINE
    if _FINBERT_PIPELINE is None:
        with _FINBERT_LOCK:
            if _FINBERT_PIPELINE is None:
                try:
                    from transformers import pipeline
                except Exception as exc:
                    raise RuntimeError(
                        "install backend ai extras: py -m pip install -e .[ai]") from exc
                # choose device if torch is available and CUDA present
                device = -1
                try:
                    import torch

                    if torch.cuda.is_available():
                        device = 0
                except Exception:
                    pass
                _FINBERT_PIPELINE = pipeline(
                    "text-classification",
                    model=model_name,
                    tokenizer=model_name,
                    device=device,
                )
    # Let the tokenizer handle truncation. Ask pipeline to return all scores
    # so we can compute a stable probability for the top label.
    output = _FINBERT_PIPELINE(
        text, truncation=True, max_length=512, return_all_scores=True)
    scores = extract_finbert_scores(output)
    best = max(scores, key=lambda item: float(item.get("score", 0.0)))
    return {"label": str(best.get("label", "neutral")), "score": float(best.get("score", 0.0))}


def extract_finbert_scores(output: object) -> list[dict[str, object]]:
    """Normalize HF pipeline outputs across transformers versions.

    Supported shapes:
    - list[dict] for a single sequence
    - list[list[dict]] for batched/single-sequence outputs in older versions
    - dict with `label`/`score` keys
    """
    if isinstance(output, dict):
        return [output]

    if isinstance(output, list) and output:
        first = output[0]
        if isinstance(first, dict):
            return [item for item in output if isinstance(item, dict)]
        if isinstance(first, list):
            nested = first
            return [item for item in nested if isinstance(item, dict)]

    raise RuntimeError(
        f"FinBERT returned unexpected sentiment result: {type(output).__name__}")


def finbert_text(state: FinancialEventState) -> str:
    parts = [state.headline, state.raw_text]
    if state.news_analysis:
        parts.extend(
            [
                state.news_analysis.summary,
                state.news_analysis.key_event,
                state.news_analysis.market_impact_summary,
            ]
        )
    return " ".join(part for part in parts if part)


def normalize_finbert_label(label: str) -> str:
    normalized = label.strip().lower()
    if normalized in {"positive", "bullish", "label_2", "label-2", "label2", "label_02", "label_ 2"}:
        return "positive"
    if normalized in {"negative", "bearish", "label_0", "label-0", "label0"}:
        return "negative"
    return "neutral"


def truncate_reason(reason: str) -> str:
    return reason if len(reason) <= 180 else reason[:177].rstrip() + "..."
