"""The State Python client.

Ten lines to a ``LocationState``::

    import asyncio
    from the_state_sdk import TheStateClient

    async def main():
        async with TheStateClient(api_key="sk-...") as client:
            state = await client.get_state("New York, NY")
            print(state.operational_state, state.risk_score)

    asyncio.run(main())
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from the_state_sdk.exceptions import NotFoundError, RateLimitError, TheStateError
from the_state_sdk.models import Brief, LocationState, Watchlist

DEFAULT_BASE_URL = "https://api.thestate.io"


def _raise_for_status(response: httpx.Response) -> None:
    if response.is_success:
        return
    code = response.status_code
    try:
        detail = response.json().get("detail", response.text)
    except Exception:
        detail = response.text
    message = f"The State API error {code}: {detail}"
    if code == 404:
        raise NotFoundError(message, status_code=code)
    if code == 429:
        raise RateLimitError(message, status_code=code)
    raise TheStateError(message, status_code=code)


class TheStateClient:
    """Async client. Pass ``http_client`` to inject a transport in tests."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._owned = http_client is None
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = http_client or httpx.AsyncClient(
            base_url=base_url, headers=headers, timeout=30.0
        )

    async def aclose(self) -> None:
        if self._owned:
            await self._client.aclose()

    async def __aenter__(self) -> TheStateClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def get_state(self, place: str, time_window: str = "24h") -> LocationState:
        resp = await self._client.get(
            "/state/location",
            params={"place": place, "time_window": time_window},
        )
        _raise_for_status(resp)
        return LocationState.model_validate(resp.json())

    async def create_watchlist(self, name: str, places: list[str], **kwargs: Any) -> Watchlist:
        body: dict[str, Any] = {"name": name, "places": places, **kwargs}
        resp = await self._client.post("/watchlists/", json=body)
        _raise_for_status(resp)
        return Watchlist.model_validate(resp.json())

    async def get_brief(self, brief_id: str) -> Brief:
        resp = await self._client.get(f"/briefs/{brief_id}")
        _raise_for_status(resp)
        return Brief.model_validate(resp.json())

    async def log_feedback(
        self,
        brief_id: str,
        *,
        false_positive: bool = False,
        outcome: str | None = None,
    ) -> None:
        resp = await self._client.post(
            "/feedback/",
            json={
                "brief_id": brief_id,
                "false_positive": false_positive,
                "outcome": outcome,
            },
        )
        _raise_for_status(resp)


class TheStateSyncClient:
    """Synchronous wrapper over :class:`TheStateClient` for non-async callers."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._async = TheStateClient(api_key=api_key, base_url=base_url, http_client=http_client)

    def _run(self, coro: Any) -> Any:
        return asyncio.run(coro)

    def get_state(self, place: str, time_window: str = "24h") -> LocationState:
        return self._run(self._async.get_state(place, time_window))

    def create_watchlist(self, name: str, places: list[str], **kwargs: Any) -> Watchlist:
        return self._run(self._async.create_watchlist(name, places, **kwargs))

    def get_brief(self, brief_id: str) -> Brief:
        return self._run(self._async.get_brief(brief_id))

    def log_feedback(
        self,
        brief_id: str,
        *,
        false_positive: bool = False,
        outcome: str | None = None,
    ) -> None:
        self._run(
            self._async.log_feedback(brief_id, false_positive=false_positive, outcome=outcome)
        )

    def close(self) -> None:
        self._run(self._async.aclose())

    def __enter__(self) -> TheStateSyncClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
