from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

import httpx


class SocrataClient:
    BASE_URL = "https://data.cityofnewyork.us/resource"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key_id: str | None = None,
        api_key_secret: str | None = None,
        app_token: str | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url or self.BASE_URL
        self.api_key_id = api_key_id
        self.api_key_secret = api_key_secret
        self.app_token = app_token
        self._owned_client = http_client is None
        self._client = http_client or httpx.AsyncClient(
            base_url=self.base_url,
            auth=self._auth(),
            headers=self._headers(),
            timeout=30,
        )

    async def close(self) -> None:
        if self._owned_client:
            await self._client.aclose()

    async def __aenter__(self) -> "SocrataClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    async def query(
        self,
        dataset_id: str,
        *,
        where: str | None = None,
        select: str | None = None,
        limit: int = 1000,
        offset: int = 0,
        order: str | None = None,
        params: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        query_params: dict[str, Any] = {"$limit": limit, "$offset": offset}
        if where:
            query_params["$where"] = where
        if select:
            query_params["$select"] = select
        if order:
            query_params["$order"] = order
        if params:
            query_params.update(params)

        response = await self._client.get(f"/{dataset_id}.json", params=query_params)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, list):
            raise ValueError("Expected Socrata response to be a list")
        return data

    async def query_since(
        self,
        dataset_id: str,
        *,
        date_field: str,
        since: datetime,
        limit: int = 1000,
        order: str | None = None,
    ) -> list[dict[str, Any]]:
        return await self.query(
            dataset_id,
            where=f"{date_field} >= '{_format_soql_datetime(since)}'",
            limit=limit,
            order=order,
        )

    def _auth(self) -> httpx.BasicAuth | None:
        if self.api_key_id and self.api_key_secret:
            return httpx.BasicAuth(self.api_key_id, self.api_key_secret)
        return None

    def _headers(self) -> dict[str, str]:
        if self.app_token:
            return {"X-App-Token": self.app_token}
        return {}


def _format_soql_datetime(value: datetime) -> str:
    utc = value.astimezone(timezone.utc)
    return utc.replace(tzinfo=None).isoformat(timespec="seconds")
