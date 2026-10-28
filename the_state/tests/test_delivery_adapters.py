import pytest
from decision_apis.delivery import (
    DeliveryAdapter,
    SlackDeliveryAdapter,
    SmsDeliveryAdapter,
    WebhookDeliveryAdapter,
)


@pytest.mark.asyncio
async def test_delivery_skeletons_share_interface():
    adapters = [
        SmsDeliveryAdapter(),
        SlackDeliveryAdapter(),
        WebhookDeliveryAdapter(),
    ]

    for adapter in adapters:
        assert isinstance(adapter, DeliveryAdapter)

        brief_result = await adapter.send_brief(
            destination="ops@example.test",
            brief={"id": "brief-1", "place": "New York, NY"},
        )
        alert_result = await adapter.send_alert(
            destination="ops@example.test",
            state_change={"current_state": "watch"},
        )

        assert brief_result.channel == adapter.channel
        assert alert_result.channel == adapter.channel
        assert brief_result.destination == "ops@example.test"
        assert alert_result.destination == "ops@example.test"
        assert brief_result.status == "skipped"
        assert alert_result.status == "skipped"
        assert "no provider call made" in brief_result.detail
        assert brief_result.metadata == {"payload_type": "dict"}
