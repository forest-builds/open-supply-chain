import json
from collections.abc import Awaitable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable, Literal

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

PaymentMode = Literal["disabled", "mock", "x402_placeholder", "x402"]

_DEFAULT_FACILITATOR_URL = "https://x402.org/facilitator"
_NETWORK_ALIASES = {
    "base": "eip155:8453",
    "base-mainnet": "eip155:8453",
    "base_sepolia": "eip155:84532",
    "base-sepolia": "eip155:84532",
}
_USDC_ASSETS_BY_NETWORK = {
    "eip155:8453": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
    "eip155:84532": "0x036CbD53842c5426634e7929541eC2318f3dCF7e",
}

_PaymentMiddlewareCallable = Callable[
    [Request, Callable[[Request], Awaitable[Response]]],
    Awaitable[Response],
]


@dataclass
class PaymentConfig:
    mode: PaymentMode = "disabled"
    wallet_address: str = ""
    network: str = "eip155:84532"
    price_usd: float = 0.01
    asset: str = "USDC"
    mock_token: str = "mock-paid"
    facilitator_url: str = _DEFAULT_FACILITATOR_URL
    route_method: str = "POST"
    description: str = ""
    mime_type: str = "application/json"


class X402Middleware(BaseHTTPMiddleware):
    """
    Mode-aware payment gate for explicit demo endpoints.

    disabled:
        Allows all requests through.
    mock:
        Requires X-Payment to match mock_token.
    x402_placeholder:
        Returns an x402-shaped 402 response when X-Payment is absent. When the
        header is present, the request passes through; real verification belongs
        where this placeholder currently accepts the header.
    x402:
        Uses the official x402 Python SDK to return protocol-native payment
        requirements, verify PAYMENT-SIGNATURE, settle successful responses, and
        attach PAYMENT-RESPONSE.
    """

    def __init__(
        self,
        app: Any,
        configs: dict[str, PaymentConfig],
        facilitator_client: Any | None = None,
        sync_facilitator_on_start: bool = True,
    ) -> None:
        super().__init__(app)
        self.configs = configs  # exact path -> PaymentConfig
        self._x402_middleware = self._build_x402_middleware(
            facilitator_client=facilitator_client,
            sync_facilitator_on_start=sync_facilitator_on_start,
        )

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        config = self._match_config(request.url.path)
        if config is None or config.mode == "disabled":
            return await call_next(request)

        if config.mode == "x402":
            if self._x402_middleware is None:
                return self._x402_setup_error(config)
            return await self._x402_middleware(request, call_next)

        payment_header = request.headers.get("X-Payment")
        if config.mode == "mock":
            if payment_header == config.mock_token:
                return await call_next(request)
            return self._mock_payment_required(request.url.path, config)

        if not payment_header:
            return self._x402_payment_required(request.url.path, config)

        # TODO: verify x402 payment proof before proceeding.
        return await call_next(request)

    def _match_config(self, path: str) -> PaymentConfig | None:
        return self.configs.get(path)

    def _build_x402_middleware(
        self,
        facilitator_client: Any | None,
        sync_facilitator_on_start: bool,
    ) -> _PaymentMiddlewareCallable | None:
        x402_configs = {
            path: config for path, config in self.configs.items() if config.mode == "x402"
        }
        if not x402_configs:
            return None

        for path, config in x402_configs.items():
            if not config.wallet_address:
                raise ValueError(f"x402 mode for {path} requires wallet_address")

        facilitator_urls = {config.facilitator_url for config in x402_configs.values()}
        if len(facilitator_urls) > 1 and facilitator_client is None:
            raise ValueError("X402Middleware supports one facilitator_url per middleware instance")

        from x402 import x402ResourceServer
        from x402.http import FacilitatorConfig, HTTPFacilitatorClient, PaymentOption
        from x402.http.middleware.fastapi import payment_middleware
        from x402.http.types import RouteConfig
        from x402.mechanisms.evm.exact import ExactEvmServerScheme

        facilitator = facilitator_client or HTTPFacilitatorClient(
            FacilitatorConfig(url=next(iter(facilitator_urls)))
        )
        server = x402ResourceServer(facilitator)

        for network in {_normalize_network(config.network) for config in x402_configs.values()}:
            server.register(network, ExactEvmServerScheme())  # type: ignore[no-untyped-call]

        routes = {}
        for path, config in x402_configs.items():
            route_key = f"{config.route_method.upper()} {path}"
            routes[route_key] = RouteConfig(
                accepts=PaymentOption(
                    scheme="exact",
                    pay_to=config.wallet_address,
                    price=_format_usd_price(config.price_usd),
                    network=_normalize_network(config.network),
                    max_timeout_seconds=300,
                ),
                description=config.description or f"Access to {path}",
                mime_type=config.mime_type,
            )

        return payment_middleware(
            routes,
            server,
            sync_facilitator_on_start=sync_facilitator_on_start,
        )

    def _mock_payment_required(self, path: str, config: PaymentConfig) -> Response:
        body = {
            "error": "Payment Required",
            "mode": "mock",
            "accepts": [
                {
                    "scheme": "mock",
                    "resource": path,
                    "description": f"Mock paid access to {path}",
                    "header": "X-Payment",
                    "value": config.mock_token,
                }
            ],
        }
        return Response(
            content=json.dumps(body),
            status_code=402,
            media_type="application/json",
        )

    def _x402_payment_required(self, path: str, config: PaymentConfig) -> Response:
        network = _normalize_network(config.network)
        body = {
            "error": "Payment Required",
            "mode": "x402_placeholder",
            "accepts": [
                {
                    "scheme": "exact",
                    "network": network,
                    "maxAmountRequired": str(int(config.price_usd * 1_000_000)),
                    "resource": path,
                    "description": config.description or f"Access to {path}",
                    "mimeType": config.mime_type,
                    "payTo": config.wallet_address,
                    "maxTimeoutSeconds": 300,
                    "asset": _USDC_ASSETS_BY_NETWORK.get(network, ""),
                    "extra": {"name": config.asset, "version": "2"},
                }
            ],
        }
        return Response(
            content=json.dumps(body),
            status_code=402,
            media_type="application/json",
        )

    def _x402_setup_error(self, config: PaymentConfig) -> Response:
        body = {
            "error": "Payment configuration error",
            "mode": config.mode,
            "detail": "x402 middleware was not initialized",
        }
        return Response(
            content=json.dumps(body),
            status_code=500,
            media_type="application/json",
        )


def _normalize_network(network: str) -> str:
    return _NETWORK_ALIASES.get(network.lower(), network)


def _format_usd_price(price_usd: float) -> str:
    price = Decimal(str(price_usd))
    if price <= 0:
        raise ValueError("x402 price_usd must be greater than 0")
    normalized = format(price, "f").rstrip("0").rstrip(".")
    return f"${normalized}"
