import json
from unittest.mock import AsyncMock, patch

import pytest

from guardrails.semantic_judge import AnthropicJudge, StubJudge


@pytest.mark.asyncio
async def test_stub_judge_returns_zero():
    judge = StubJudge()
    band = await judge.classify("execute_sql_query", {"query": "SELECT 1"}, "")
    assert band == 0.0


@pytest.mark.asyncio
async def test_anthropic_judge_malformed_json_defaults_to_medium():
    judge = AnthropicJudge(api_key="test-key")

    mock_response = AsyncMock()
    mock_response.raise_for_status = lambda: None
    mock_response.json.return_value = {"content": [{"text": "not valid json at all"}]}

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None

    with patch("guardrails.semantic_judge.httpx.AsyncClient", return_value=mock_client):
        band = await judge.classify("send_payment", {"amount": 50}, "")

    assert band == 0.66
