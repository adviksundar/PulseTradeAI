from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "PulseTradeAI"
    environment: Literal["local", "dev", "staging", "prod"] = "local"
    cors_origins: list[str] = Field(default_factory=lambda: [
                                    "http://localhost:5173"])

    redis_url: str = "redis://localhost:6379/0"
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/pulsetradeai"

    openai_api_key: str | None = None
    hf_token: str | None = None
    openai_model: str = "gpt-5-nano"
    openai_fast_model: str = "gpt-5-nano"
    openai_brief_model: str = "gpt-5-mini"
    use_mock_ai: bool = True
    use_mock_market_data: bool = False
    sentiment_provider: Literal["lexicon", "finbert"] = "lexicon"
    finbert_model: str = "ProsusAI/finbert"

    finnhub_api_key: str | None = None
    finnhub_rate_limit_per_minute: int = 60
    finnhub_max_calls_per_second: int = 30
    use_finnhub_news: bool = True
    finnhub_news_symbols_per_poll: int = 1
    finnhub_news_lookback_days: int = 7
    finnhub_news_max_events_per_poll: int = 1
    finnhub_news_bootstrap_on_start: bool = True
    finnhub_news_bootstrap_symbol_limit: int = 10
    finnhub_news_bootstrap_events_per_symbol: int = 1

    tracked_tickers: list[str] = Field(
        default_factory=lambda: ["AAPL", "MSFT", "NVDA", "TSLA", "BTC-USD"])
    market_poll_seconds: float = 2.0
    news_poll_seconds: float = 6.0

    price_alert_threshold_pct: float = 2.0
    volume_alert_multiplier: float = 1.8
    sentiment_shift_threshold: float = 0.5


@lru_cache
def get_settings() -> Settings:
    return Settings()
