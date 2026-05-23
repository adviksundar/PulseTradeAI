# Multi-Agent Workflow

PulseTradeAI uses a deterministic, graph-style AI workflow. It is intentionally not a fully autonomous agent system. The backend owns routing, ordering, retries, state transitions, and broadcasts.

## Flow

```text
News Event
  -> Event Router
  -> FinancialIntelligenceOrchestrator
  -> NewsAnalysisWorkflowAgent
  -> SentimentAnalysisWorkflowAgent
  -> RiskScoringWorkflowAgent
  -> AlertDecisionWorkflowAgent
  -> MarketBriefWorkflowAgent
  -> Shared in-memory state history
  -> Redis/in-memory cache
  -> WebSocket broadcast
```

## State

The shared state object is `FinancialEventState` in `backend/app/agents/workflow/state.py`.

Agents append their own output:

- `news_analysis`
- `sentiment`
- `risk`
- `alert_decision`
- `market_brief`
- `trace`

Agents should not overwrite unrelated fields.

## Model Strategy

Default execution balances cost, reliability, and performance:

- `NewsAnalysisWorkflowAgent`: OpenAI structured extraction using `OPENAI_FAST_MODEL`.
- `SentimentAnalysisWorkflowAgent`: optional FinBERT local transformer classification with a finance-lexicon fallback.
- `RiskScoringWorkflowAgent`: deterministic scoring from sentiment plus market movement/volume context.
- `AlertDecisionWorkflowAgent`: deterministic alert policy.
- `MarketBriefWorkflowAgent`: OpenAI structured synthesis using `OPENAI_BRIEF_MODEL`.

This keeps the architecture multi-agent while avoiding five OpenAI calls for every news event. It also keeps routing, risk, and alerting predictable while allowing stronger local NLP for sentiment.

## Debug UI Counters

The dashboard debug view keeps stage cards focused on cumulative startup counters. Per-event traces are still available in the recent-events and logs sections below the graph.

For a normal OpenAI-backed run, startup counters should increase this way:

- News Analysis: one OpenAI API call per processed news event.
- Sentiment: local backend execution, zero OpenAI calls. It may use FinBERT locally when enabled.
- Risk Scoring: local backend policy, zero OpenAI calls.
- Alert Decision: local backend policy, zero OpenAI calls.
- Market Brief: one OpenAI API call per processed news event.

If 20 news events have been processed since startup, the two OpenAI stages may each show `20/20 API calls succeeded`. That does not mean one event was retried 20 times; it means 20 separate events have gone through that stage.

## Runtime Modes

Local deterministic mode:

```env
USE_MOCK_AI=true
OPENAI_API_KEY=
```

OpenAI-backed workflow:

```env
USE_MOCK_AI=false
OPENAI_API_KEY=your_key_here
OPENAI_FAST_MODEL=gpt-5-nano
OPENAI_BRIEF_MODEL=gpt-5-mini
```

Put real secrets in `.env`, not `.env.example`.

## Broadcasts

The workflow emits:

- `ai_insight`: dashboard-ready insight
- `alert`: alert object when the alert agent decides one is warranted
- `agent_state`: full structured workflow state for debugging/future UI

The `/api/agent-status` endpoint also exposes recent event traces, stage logs, poll-loop counters, and OpenAI attempt/success totals for the debug page.
