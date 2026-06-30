#!/usr/bin/env python3
"""Smoke-test a deployed Aegis-MCP API via /v1/tools/call.

Usage:
    python scripts/smoke_test.py https://your-api.onrender.com

Exits 0 if all checks pass, 1 if any fail.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

import httpx

TIMEOUT = 60.0  # Render free tier may cold-start


def _rpc(tool_name: str, arguments: dict, request_id: int) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
        "session_id": "smoke-test",
    }


def _post(base_url: str, payload: dict) -> tuple[int, Any]:
    url = f"{base_url.rstrip('/')}/v1/tools/call"
    with httpx.Client(timeout=TIMEOUT) as client:
        response = client.post(url, json=payload)
        try:
            body = response.json()
        except json.JSONDecodeError:
            body = response.text
    return response.status_code, body


def _fmt_body(body: Any) -> str:
    if isinstance(body, (dict, list)):
        return json.dumps(body, indent=2)
    return str(body)


def _is_blocked(body: Any) -> bool:
    return isinstance(body, dict) and body.get("error", {}).get("code") == -32001


def _is_escalated(body: Any) -> bool:
    return (
        isinstance(body, dict)
        and isinstance(body.get("result"), dict)
        and body["result"].get("status") == "pending_review"
    )


def check_allow(base_url: str) -> bool:
    name = "clean SELECT → ALLOW"
    payload = _rpc("execute_sql_query", {"query": "SELECT id, name FROM users LIMIT 10"}, 1)

    try:
        status, body = _post(base_url, payload)
    except httpx.HTTPError as exc:
        print(f"FAIL  {name}")
        print(f"      Request error: {exc}")
        return False

    if _is_blocked(body):
        print(f"FAIL  {name}")
        print(f"      Guardrail BLOCKED (expected ALLOW). HTTP {status}")
        print(f"      Response:\n{_fmt_body(body)}")
        return False

    if _is_escalated(body):
        print(f"FAIL  {name}")
        print(f"      Guardrail ESCALATED (expected ALLOW). HTTP {status}")
        print(f"      Response:\n{_fmt_body(body)}")
        return False

    if status >= 500:
        print(f"FAIL  {name}")
        print(
            "      Guardrail did not block/escalate, but upstream forward failed "
            f"(HTTP {status}). Set UPSTREAM_MCP_URL to a reachable endpoint "
            "(e.g. https://httpbin.org/post for a quick demo)."
        )
        print(f"      Response:\n{_fmt_body(body)}")
        return False

    if status >= 400:
        print(f"FAIL  {name}")
        print(f"      Unexpected HTTP {status} (expected 2xx after ALLOW).")
        print(f"      Response:\n{_fmt_body(body)}")
        return False

    print(f"PASS  {name}  (HTTP {status}, forwarded past guardrail)")
    return True


def check_block(base_url: str) -> bool:
    name = "DROP TABLE → BLOCK"
    payload = _rpc("execute_sql_query", {"query": "DROP TABLE users"}, 2)

    try:
        status, body = _post(base_url, payload)
    except httpx.HTTPError as exc:
        print(f"FAIL  {name}")
        print(f"      Request error: {exc}")
        return False

    if not _is_blocked(body):
        print(f"FAIL  {name}")
        print(f"      Expected JSON-RPC error -32001 (BLOCK). HTTP {status}")
        print(f"      Response:\n{_fmt_body(body)}")
        return False

    print(f"PASS  {name}  (HTTP {status}, code -32001)")
    return True


def check_escalate(base_url: str) -> bool:
    name = "send_payment $150 → ESCALATE (pending_review)"
    payload = _rpc("send_payment", {"amount": 150}, 3)

    try:
        status, body = _post(base_url, payload)
    except httpx.HTTPError as exc:
        print(f"FAIL  {name}")
        print(f"      Request error: {exc}")
        return False

    if not _is_escalated(body):
        print(f"FAIL  {name}")
        print(f"      Expected result.status=pending_review. HTTP {status}")
        if _is_blocked(body):
            print("      Got BLOCK instead — check risk scorer / policy config.")
        print(f"      Response:\n{_fmt_body(body)}")
        return False

    pending_id = body.get("result", {}).get("pending_id")
    print(f"PASS  {name}  (HTTP {status}, pending_id={pending_id})")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test deployed Aegis-MCP API")
    parser.add_argument(
        "base_url",
        help="API base URL, e.g. https://aegis-mcp-api.onrender.com",
    )
    args = parser.parse_args()

    print(f"Target: {args.base_url.rstrip('/')}/v1/tools/call")
    print("-" * 60)

    results = [
        check_allow(args.base_url),
        check_block(args.base_url),
        check_escalate(args.base_url),
    ]

    print("-" * 60)
    passed = sum(results)
    total = len(results)
    if all(results):
        print(f"All {total} checks PASSED.")
        return 0
    print(f"{passed}/{total} checks passed.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
