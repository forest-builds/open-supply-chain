from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from payments import PaymentConfig, X402Middleware
from x402.http.constants import (
    PAYMENT_REQUIRED_HEADER,
    PAYMENT_RESPONSE_HEADER,
    PAYMENT_SIGNATURE_HEADER,
)
from x402.http.utils import (
    decode_payment_required_header,
    decode_payment_response_header,
    encode_payment_signature_header,
)
from x402.schemas import (
    PaymentPayload,
    PaymentRequired,
    PaymentRequirements,
    SettleResponse,
    SupportedKind,
    SupportedResponse,
    VerifyResponse,
)


class FakeFacilitatorClient:
    def __init__(self, network: str = "eip155:84532", valid: bool = True) -> None:
        self.network = network
        self.valid = valid

    def get_supported(self) -> SupportedResponse:
        return SupportedResponse(
            kinds=[
                SupportedKind(
                    x402_version=2,
                    scheme="exact",
                    network=self.network,
                )
            ]
        )

    async def verify(
        self,
        payment_payload: Any,
        payment_requirements: Any,
    ) -> VerifyResponse:
        if self.valid:
            return VerifyResponse(is_valid=True, payer="0xpayer")
        return VerifyResponse(is_valid=False, invalid_reason="test-payment-not-valid")

    async def settle(
        self,
        payment_payload: Any,
        payment_requirements: Any,
    ) -> SettleResponse:
        return SettleResponse(
            success=True,
            transaction="0xsettled",
            network=self.network,
        )


def _payment_app(config: PaymentConfig, **middleware_kwargs: Any) -> FastAPI:
    app = FastAPI()
    app.add_middleware(
        X402Middleware,
        configs={"/decisions/evaluate": config},
        **middleware_kwargs,
    )

    @app.post("/decisions/evaluate")
    async def evaluate() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/state/location")
    async def state_location() -> dict[str, bool]:
        return {"ok": True}

    return app


@pytest.mark.asyncio
async def test_decisions_evaluate_is_open_when_payment_mode_disabled(client: AsyncClient) -> None:
    response = await client.post("/decisions/evaluate", json={})

    assert response.status_code == 200
    assert response.json()["status"] == "evaluated"


@pytest.mark.asyncio
async def test_mock_payment_mode_requires_mock_header() -> None:
    app = _payment_app(PaymentConfig(mode="mock", mock_token="paid"))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        unpaid = await client.post("/decisions/evaluate")
        paid = await client.post("/decisions/evaluate", headers={"X-Payment": "paid"})
        ungated = await client.get("/state/location")

    assert unpaid.status_code == 402
    assert unpaid.json()["mode"] == "mock"
    assert unpaid.json()["accepts"][0]["value"] == "paid"
    assert paid.status_code == 200
    assert ungated.status_code == 200


@pytest.mark.asyncio
async def test_x402_placeholder_mode_returns_payment_requirements() -> None:
    app = _payment_app(
        PaymentConfig(
            mode="x402_placeholder",
            wallet_address="0x0000000000000000000000000000000000000000",
        )
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        unpaid = await client.post("/decisions/evaluate")
        placeholder_paid = await client.post(
            "/decisions/evaluate",
            headers={"X-Payment": "placeholder-proof"},
        )

    assert unpaid.status_code == 402
    assert unpaid.json()["mode"] == "x402_placeholder"
    assert unpaid.json()["accepts"][0]["scheme"] == "exact"
    assert placeholder_paid.status_code == 200


@pytest.mark.asyncio
async def test_x402_mode_returns_protocol_payment_requirements_header() -> None:
    wallet = "0x0000000000000000000000000000000000000000"
    app = _payment_app(
        PaymentConfig(
            mode="x402",
            wallet_address=wallet,
            network="eip155:84532",
            price_usd=0.01,
        ),
        facilitator_client=FakeFacilitatorClient(),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        unpaid = await client.post("/decisions/evaluate")
        legacy_header = await client.post(
            "/decisions/evaluate",
            headers={"X-Payment": "not-a-v2-payment-signature"},
        )
        ungated = await client.get("/state/location")

    assert unpaid.status_code == 402
    payment_required_header = unpaid.headers[PAYMENT_REQUIRED_HEADER]
    payment_required = decode_payment_required_header(payment_required_header)
    assert isinstance(payment_required, PaymentRequired)
    requirement = payment_required.accepts[0]
    assert isinstance(requirement, PaymentRequirements)
    assert payment_required.x402_version == 2
    assert requirement.scheme == "exact"
    assert requirement.network == "eip155:84532"
    assert requirement.amount == "10000"
    assert requirement.pay_to == wallet
    assert legacy_header.status_code == 402
    assert ungated.status_code == 200

    payment = PaymentPayload(payload={"test": "signed"}, accepted=requirement)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        paid = await client.post(
            "/decisions/evaluate",
            headers={PAYMENT_SIGNATURE_HEADER: encode_payment_signature_header(payment)},
        )

    assert paid.status_code == 200
    settlement = decode_payment_response_header(paid.headers[PAYMENT_RESPONSE_HEADER])
    assert settlement.success is True
    assert settlement.transaction == "0xsettled"
