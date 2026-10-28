from __future__ import annotations

from typing import Any, TypeVar

import httpx
from pydantic import BaseModel

from mcp_server.tools import (
    GenerateOperationalBriefInput,
    GetCurrentStateInput,
    WatchEntityInput,
)

InputModel = TypeVar("InputModel", bound=BaseModel)


class TheStateMcpClient:
    def __init__(
        self,
        *,
        base_url: str = "http://localhost:8000",
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._owned_client = http_client is None
        self._client = http_client or httpx.AsyncClient(base_url=base_url)

    async def close(self) -> None:
        if self._owned_client:
            await self._client.aclose()

    async def __aenter__(self) -> "TheStateMcpClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    async def get_current_state(
        self,
        payload: GetCurrentStateInput | dict[str, Any],
    ) -> dict[str, Any]:
        body = _coerce(GetCurrentStateInput, payload)
        response = await self._client.get(
            "/state/location",
            params=body.model_dump(),
        )
        response.raise_for_status()
        return response.json()

    async def generate_operational_brief(
        self,
        payload: GenerateOperationalBriefInput | dict[str, Any],
    ) -> dict[str, Any]:
        body = _coerce(GenerateOperationalBriefInput, payload)
        request_body = body.model_dump(mode="json", exclude_none=True)
        if body.watchlist_id is not None and body.evaluation_result_id is None:
            evaluation = await self._evaluate_watchlist(str(body.watchlist_id))
            request_body["evaluation_result_id"] = evaluation["id"]

        response = await self._client.post("/briefs/generate", json=request_body)
        response.raise_for_status()
        return response.json()

    async def watch_entity(
        self,
        payload: WatchEntityInput | dict[str, Any],
    ) -> dict[str, Any]:
        body = _coerce(WatchEntityInput, payload)
        response = await self._client.post(
            "/watchlists/",
            json=body.model_dump(mode="json", exclude_none=True),
        )
        response.raise_for_status()
        return response.json()

    async def _evaluate_watchlist(self, watchlist_id: str) -> dict[str, Any]:
        response = await self._client.post(f"/watchlists/{watchlist_id}/evaluate")
        response.raise_for_status()
        return response.json()


def _coerce(
    model_type: type[InputModel],
    payload: InputModel | dict[str, Any],
) -> InputModel:
    if isinstance(payload, model_type):
        return payload
    return model_type.model_validate(payload)
