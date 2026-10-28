from __future__ import annotations

from decision_apis.delivery.base import DeliveryPayload, DeliveryResult, skeleton_result


class WebhookDeliveryAdapter:
    channel = "webhook"

    async def send_brief(
        self,
        destination: str,
        brief: DeliveryPayload,
    ) -> DeliveryResult:
        return skeleton_result(
            channel=self.channel,
            destination=destination,
            payload_kind="brief",
            payload=brief,
        )

    async def send_alert(
        self,
        destination: str,
        state_change: DeliveryPayload,
    ) -> DeliveryResult:
        return skeleton_result(
            channel=self.channel,
            destination=destination,
            payload_kind="alert",
            payload=state_change,
        )
