from typing import Any

import httpx

from app.config import settings


class OneDBAClient:
    """Async client for the OneDBA external agent API."""

    def __init__(
        self,
        base_url: str | None = None,
        access_token: str | None = None,
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.base_url = (base_url or settings.ONEDBA_BASE_URL).rstrip("/")
        self.access_token = access_token if access_token is not None else settings.ONEDBA_ACCESS_TOKEN
        self.timeout = timeout
        self.transport = transport

    def _get_headers(self) -> dict[str, str]:
        return {
            "accessToken": self.access_token,
            "Content-Type": "application/json",
        }

    async def list_databases(
        self,
        keyword: str = "",
        env_type: str = "test",
        instance_type: str = "acs_rds",
        main_body: str = "shizhuang",
        page: int = 1,
        size: int = 30,
    ) -> list[dict[str, Any]]:
        """Return database schemas available to the current OneDBA token."""

        url = f"{self.base_url}/api/external/v1/agent/instance/schema/user/list"
        params: dict[str, Any] = {
            "queryType": "select",
            "page": page,
            "size": size,
            "envType": env_type,
            "instanceType": instance_type,
            "mainBody": main_body,
        }
        if keyword:
            params["keyword"] = keyword

        async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
            response = await client.get(url, headers=self._get_headers(), params=params)
            response.raise_for_status()
            payload = response.json()

        self._raise_for_api_error(payload)
        data = payload.get("data") or {}
        return data.get("items") or []

    async def execute_sql(self, schema_id: int, sql: str, query_timeout: int = 30) -> dict[str, Any]:
        """Execute SQL on a OneDBA schema and return raw OneDBA data."""

        url = f"{self.base_url}/api/external/v1/agent/query"
        payload = {
            "schemaId": schema_id,
            "sqlText": sql,
            "queryTimeout": query_timeout,
        }

        async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
            response = await client.post(url, headers=self._get_headers(), json=payload)
            response.raise_for_status()
            result = response.json()

        self._raise_for_api_error(result)
        return result.get("data") or {}

    @staticmethod
    def _raise_for_api_error(payload: dict[str, Any]) -> None:
        if payload.get("code") not in (0, "0", None):
            message = payload.get("message") or payload.get("msg") or "unknown error"
            raise RuntimeError(f"OneDBA API error: {message}")


onedba_client = OneDBAClient()
