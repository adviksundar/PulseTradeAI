import pytest

from app.agents.alert_decision import AlertDecisionAgent
from app.core.config import Settings
from app.domain.schemas import MarketTick


@pytest.mark.asyncio
async def test_price_move_alert_is_created() -> None:
    agent = AlertDecisionAgent(Settings(price_alert_threshold_pct=1.0))
    alerts = await agent.from_tick(
        MarketTick(ticker="TSLA", price=105.0, previous_price=100.0, volume=100, previous_volume=100)
    )
    assert alerts
    assert alerts[0].alert_type == "price_move"

