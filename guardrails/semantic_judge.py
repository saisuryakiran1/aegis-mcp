from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod

import httpx

from config import get_config

logger = logging.getLogger(__name__)

VALID_BANDS = {0.0, 0.33, 0.66, 1.0}

SYSTEM_PROMPT = (
    "You are a security risk classifier for MCP tool calls. "
    "Return ONLY a JSON object with this exact shape: "
    '{"risk_band": 0.0|0.33|0.66|1.0, "reason": "<one short sentence>"}. '
    "No markdown, no extra text. "
    "risk_band meanings: 0.0=safe, 0.33=low, 0.66=medium, 1.0=high."
)


class SemanticJudge(ABC):
    @abstractmethod
    async def classify(self, tool_name: str, arguments: dict, context: str) -> float:
        ...


class StubJudge(SemanticJudge):
    async def classify(self, tool_name: str, arguments: dict, context: str) -> float:
        return 0.0


class AnthropicJudge(SemanticJudge):
    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6"):
        self.api_key = api_key
        self.model = model

    async def classify(self, tool_name: str, arguments: dict, context: str) -> float:
        user_content = json.dumps(
            {"tool_name": tool_name, "arguments": arguments, "context": context}
        )
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": self.api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "max_tokens": 200,
                        "system": SYSTEM_PROMPT,
                        "messages": [{"role": "user", "content": user_content}],
                    },
                )
                response.raise_for_status()
                data = response.json()
                text = data["content"][0]["text"].strip()
                return self._parse_band(text)
        except Exception as exc:
            logger.warning("AnthropicJudge API error: %s", exc)
            return 0.66

    def _parse_band(self, text: str) -> float:
        try:
            parsed = json.loads(text)
            band = float(parsed["risk_band"])
            if band not in VALID_BANDS:
                raise ValueError(f"Invalid risk_band: {band}")
            return band
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            logger.warning("AnthropicJudge malformed JSON output: %s — %s", text, exc)
            return 0.66


def create_judge() -> SemanticJudge:
    cfg = get_config()
    if cfg.semantic_judge == "anthropic":
        import os

        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is required when semantic_judge=anthropic")
        return AnthropicJudge(api_key=api_key)
    return StubJudge()
