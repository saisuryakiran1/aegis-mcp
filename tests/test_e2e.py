import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from config import load_config
from hitl import queue as hitl_queue
from main import app


@pytest.fixture
def client():
    load_config()
    hitl_queue.store._store.clear()
    return TestClient(app)


def _rpc(tool_name: str, arguments: dict, request_id: int = 1) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
        "session_id": "test-session",
    }


def _mock_upstream(return_value: dict):
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = return_value

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    return patch("main.httpx.AsyncClient", return_value=mock_client)


def test_allow_flow_forwards_upstream(client):
    payload = _rpc("execute_sql_query", {"query": "SELECT id FROM users"})
    upstream_response = {"jsonrpc": "2.0", "id": 1, "result": {"rows": [[1]]}}

    with _mock_upstream(upstream_response):
        response = client.post("/v1/tools/call", json=payload)

    assert response.status_code == 200
    assert response.json() == upstream_response


def test_block_flow_never_forwards(client):
    payload = _rpc("execute_sql_query", {"query": "DROP TABLE users"})

    with _mock_upstream({"jsonrpc": "2.0", "id": 1, "result": {}}):
        response = client.post("/v1/tools/call", json=payload)

    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == -32001


def test_escalate_flow_pending_review(client):
    payload = _rpc("send_payment", {"amount": 150})

    with _mock_upstream({"jsonrpc": "2.0", "id": 1, "result": {}}):
        response = client.post("/v1/tools/call", json=payload)

    data = response.json()
    assert response.status_code == 200
    assert data["result"]["status"] == "pending_review"
    assert "pending_id" in data["result"]

    pending_id = data["result"]["pending_id"]
    get_resp = client.get(f"/v1/pending/{pending_id}")
    assert get_resp.json()["status"] == "pending"


def test_approve_forwards_upstream(client):
    with _mock_upstream({"jsonrpc": "2.0", "id": 1, "result": {}}):
        escalate = client.post(
            "/v1/tools/call",
            json=_rpc("send_payment", {"amount": 150}, request_id=2),
        )

    pending_id = escalate.json()["result"]["pending_id"]
    upstream_response = {"jsonrpc": "2.0", "id": 2, "result": {"payment_id": "p-1"}}

    with _mock_upstream(upstream_response):
        approve = client.post(f"/v1/pending/{pending_id}/approve", json={"reviewer": "alice"})

    assert approve.status_code == 200
    assert approve.json()["status"] == "approved"
    assert approve.json()["result"] == upstream_response
