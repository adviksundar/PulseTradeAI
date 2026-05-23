export type SentimentLabel = "Bullish" | "Neutral" | "Bearish";
export type RiskLevel = "Low" | "Medium" | "High";

export interface MarketTick {
  event_id: string;
  ticker: string;
  price: number;
  previous_price: number;
  volume: number;
  previous_volume: number;
  source: string;
  timestamp: string;
}

export interface MarketHistoryPoint {
  ticker: string;
  price: number;
  volume: number;
  timestamp: string;
}

export interface MarketHistory {
  ticker: string;
  range: string;
  source: string;
  points: MarketHistoryPoint[];
}

export interface AIInsight {
  event_id: string;
  ticker: string;
  summary: string;
  key_events: string[];
  sentiment: SentimentLabel;
  sentiment_score: number;
  confidence: number;
  sentiment_source?: string;
  raw_sentiment_score?: number;
  risk_level: RiskLevel;
  market_impact: string;
  source_event_id: string;
  created_at: string;
}

export interface Alert {
  alert_id: string;
  ticker: string;
  alert_type:
    | "price_move"
    | "volume_spike"
    | "sentiment_shift"
    | "breaking_news";
  title: string;
  message: string;
  severity: RiskLevel;
  confidence: number;
  created_at: string;
  related_event_id?: string;
}

export interface DashboardSnapshot {
  ticks: MarketTick[];
  insights: AIInsight[];
  alerts: Alert[];
}

export interface Watchlist {
  tickers: string[];
  rejected: string[];
}

export interface AgentTrace {
  agent: string;
  model: string;
  status: "ok" | "fallback" | "error";
  calls_made: number;
  successful_calls: number;
  uses_openai: boolean;
  message?: string | null;
  created_at: string;
}

export interface AgentStageDefinition {
  agent: string;
  label: string;
  description: string;
  uses_openai: boolean;
  model: string;
}

export interface AgentEventSummary {
  event_id: string;
  ticker: string;
  headline: string;
  timestamp: string;
  trace: AgentTrace[];
}

export interface AgentWorkflowLog {
  event_id: string;
  ticker: string;
  headline: string;
  agent: string;
  status: "ok" | "fallback" | "error";
  model: string;
  uses_openai: boolean;
  calls_made: number;
  successful_calls: number;
  message?: string | null;
  created_at: string;
}

export interface AgentStatus {
  openai_enabled: boolean;
  use_mock_ai: boolean;
  fast_model: string;
  brief_model: string;
  processed_events: number;
  total_openai_calls: number;
  total_openai_attempts: number;
  total_openai_successes: number;
  stage_call_counts: Record<string, number>;
  stage_success_counts: Record<string, number>;
  news_poll_seconds: number;
  market_poll_seconds: number;
  news_loop_count: number;
  news_events_seen: number;
  market_loop_count: number;
  last_news_loop_started_at: string | null;
  last_news_loop_completed_at: string | null;
  last_news_event_at: string | null;
  last_market_loop_at: string | null;
  latest_completed_at: string | null;
  stage_definitions: AgentStageDefinition[];
  latest_trace: AgentTrace[];
  latest_ticker: string | null;
  latest_headline: string | null;
  recent_events: AgentEventSummary[];
  logs: AgentWorkflowLog[];
}

export interface StreamMessage<T = unknown> {
  event: "market_tick" | "ai_insight" | "alert" | "news_event" | "agent_state";
  data: T;
}
