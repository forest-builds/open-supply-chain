from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping, Protocol, runtime_checkable

DeliveryPayload = Mapping[str, Any] | str
DeliveryStatus = Literal["skipped", "queued", "sent", "failed"]


@dataclass(frozen=True)
class DeliveryResult:
    channel: str
    destination: str
    status: DeliveryStatus
    detail: str
    provider_message_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class DeliveryAdapter(Protocol):
    channel: str

    async def send_brief(
        self,
        destination: str,
        brief: DeliveryPayload,
    ) -> DeliveryResult: ...

    async def send_alert(
        self,
        destination: str,
        state_change: DeliveryPayload,
    ) -> DeliveryResult: ...


def skeleton_result(
    *,
    channel: str,
    destination: str,
    payload_kind: str,
    payload: DeliveryPayload,
) -> DeliveryResult:
    return DeliveryResult(
        channel=channel,
        destination=destination,
        status="skipped",
        detail=f"{channel} skeleton captured {payload_kind}; no provider call made",
        metadata={"payload_type": type(payload).__name__},
    )
