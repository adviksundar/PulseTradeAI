# AI Pipeline

PulseTradeAI is structured like a small AI orchestration system.

```text
News Event Arrives
-> News Analysis Agent
-> Sentiment Agent
-> Risk Scoring Agent
-> Alert Decision Agent
-> Market Brief Agent
-> Dashboard Streaming Agent
```

## Current Implementation

The current backend includes a deterministic graph-style workflow in `backend/app/agents/workflow/`.

- `NewsAnalysisWorkflowAgent`
- `SentimentAnalysisWorkflowAgent`
- `RiskScoringWorkflowAgent`
- `AlertDecisionWorkflowAgent`
- `MarketBriefWorkflowAgent`
- `FinancialIntelligenceOrchestrator`

Each agent receives and updates a shared `FinancialEventState`.

## OpenAI Mode

When `USE_MOCK_AI=false` and `OPENAI_API_KEY` is present, the news-analysis and market-brief agents call OpenAI with strict JSON schemas and Pydantic validation. Sentiment, risk, and alert-decision agents are deterministic policy agents to keep the workflow predictable and low-cost. If OpenAI is unavailable, deterministic fallbacks keep the stream alive.

Recommended output fields:

- `summary`
- `key_events`
- `sentiment`
- `sentiment_score`
- `confidence`
- `risk_level`
- `market_impact`

Keep model output validation strict with Pydantic. Failed parses fall back to deterministic outputs and create diagnostic logs.

## Cost Profile

The current workflow is intentionally not five OpenAI calls per event.

- OpenAI call: News Analysis Agent.
- Optional FinBERT local transformer: Sentiment Agent when `SENTIMENT_PROVIDER=finbert`.
- Local backend fallback: finance-oriented phrase scoring, negation handling, low-impact context detection, and market-move confirmation.
- Local backend policy: Risk Scoring Agent.
- Local backend policy: Alert Decision Agent.
- OpenAI call: Market Brief Agent.

This makes the system easier to debug and cheaper to run while still demonstrating a stateful graph-style AI workflow. The dashboard debug page shows both per-event execution and cumulative counts since backend startup.

## FinBERT Sentiment

FinBERT can be enabled with:

```env
SENTIMENT_PROVIDER=finbert
FINBERT_MODEL=ProsusAI/finbert
```

Install the optional backend AI dependencies first:

```bash
cd backend
py -m pip install -e ".[ai]"
```

The sentiment agent lazy-loads the HuggingFace pipeline on first use. If the model or dependencies are unavailable, the workflow falls back to the local finance lexicon scorer and keeps streaming.

### Notes on recent improvements

- Thread-safe FinBERT load: the backend now acquires a lock before initializing the HuggingFace `pipeline` to avoid race conditions during concurrent startup or first inference.
- Device detection: the pipeline will prefer GPU when available but falls back to CPU on developer machines; a lightweight test script `backend/scripts/check_finbert.py` can validate local setup.
- Robust output parsing: FinBERT/HuggingFace outputs can vary; the classifier now handles list/dict/string shapes and normalizes labels (LABEL_0/1/2 variants and textual labels like `positive`/`neutral`/`negative`).
- Confidence & score calibration: raw model scores and lexicon-derived scores are softly normalized (tanh-like compression) and calibrated to avoid extreme, overconfident outputs (confidence range clamped and smoothed).
- Provenance fields: sentiment outputs include `raw_score` and `source` so downstream logic and the UI can show which provider (finbert vs lexicon) produced the signal and the original numeric score.
- Token-aware trimming: news-analysis prompts now send a compact `article_excerpt` trimmed by characters or tokens (uses `tiktoken` when available) to reduce OpenAI token usage and mitigate truncated/invalid JSON responses.
- HF_TOKEN support: if `HF_TOKEN` is present in `.env` (or `Settings.hf_token`) the backend exports it at startup to allow authenticated downloads from the HuggingFace Hub.
