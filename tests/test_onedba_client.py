import httpx
import pytest

from app.client.onedba_client import OneDBAClient


@pytest.mark.asyncio
async def test_list_databases_parses_items():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["accessToken"] == "token"
        assert request.url.params["keyword"] == "onedba"
        return httpx.Response(200, json={"code": 0, "data": {"items": [{"schemaId": 1}]}})

    transport = httpx.MockTransport(handler)
    client = OneDBAClient(base_url="https://example.test", access_token="token", transport=transport)
    assert await client.list_databases(keyword="onedba") == [{"schemaId": 1}]


@pytest.mark.asyncio
async def test_execute_sql_parses_data():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["payload"] = request.content
        return httpx.Response(200, json={"code": 0, "data": {"columnNames": [], "columnDatas": []}})

    transport = httpx.MockTransport(handler)
    client = OneDBAClient(base_url="https://example.test", access_token="token", transport=transport)
    assert await client.execute_sql(12, "SELECT 1") == {"columnNames": [], "columnDatas": []}
