from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import get_config, get_policy, load_config
from guardrails.allowlist_engine import ValidationResult, check_max_length, validate_sql
from guardrails.risk_scorer import score_call
from guardrails.semantic_judge import create_judge
from hitl import queue as hitl_queue
from hitl.webhook import notify_escalation

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("aegis")

app = FastAPI(title="Aegis-MCP")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ReviewerBody(BaseModel):
    reviewer: str = "human"


def _resolve_upstream_url() -> str:
    url = os.environ.get("UPSTREAM_MCP_URL") or get_config().upstream_url
    if not url:
        raise RuntimeError("UPSTREAM_MCP_URL environment variable is not set")
    return url


def _log_decision(tool_name: str, action: str, risk_score: float, session_id: str) -> None:
    logger.info(
        json.dumps(
            {
                "tool_name": tool_name,
                "action": action,
                "risk_score": risk_score,
                "session_id": session_id,
            }
        )
    )


def run_structural_validation(tool_name: str, arguments: dict) -> ValidationResult:
    policy = get_policy(tool_name)
    if policy is None:
        return ValidationResult(
            passed=False,
            statement_type="UNKNOWN",
            reason=f"No policy for tool '{tool_name}'",
            failed_rule="policy",
            rule_action="BLOCK",
        )

    for rule in policy.rules:
        if rule.type == "ast_allowlist":
            query = str(arguments.get("query", ""))
            result = validate_sql(query, rule.allowed_statement_types)
            if not result.passed:
                result.rule_action = rule.action.value
                return result
        elif rule.type == "max_length":
            value = str(arguments.get(rule.parameter, ""))
            result = check_max_length(value, rule.limit)
            if not result.passed:
                result.rule_action = rule.action.value
                return result
        elif rule.type == "threshold_check":
            raw = arguments.get(rule.parameter, 0)
            try:
                amount = float(raw)
            except (TypeError, ValueError):
                amount = 0.0
            if amount > rule.max_value:
                return ValidationResult(
                    passed=False,
                    statement_type="THRESHOLD",
                    reason=f"{rule.parameter} {amount} exceeds max {rule.max_value}",
                    failed_rule="threshold_check",
                    rule_action=rule.action.value,
                )

    return ValidationResult(passed=True, statement_type="OK", reason=None)


def _block_error(explanation: str, risk_score: float, request_id: Any) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {
            "code": -32001,
            "message": explanation,
            "data": {"risk_score": risk_score, "explanation": explanation},
        },
    }


async def _forward_upstream(payload: dict) -> dict:
    upstream_url = _resolve_upstream_url()
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(upstream_url, json=payload)
        response.raise_for_status()
        return response.json()


@app.on_event("startup")
async def startup() -> None:
    load_config()


@app.post("/v1/tools/call")
async def tools_call(payload: dict) -> dict:
    request_id = payload.get("id")
    session_id = payload.get("session_id", "")

    if payload.get("method") != "tools/call":
        return _block_error("Invalid JSON-RPC method", 1.0, request_id)

    params = payload.get("params") or {}
    tool_name = params.get("name")
    arguments = params.get("arguments") or {}

    if not tool_name:
        return _block_error("Missing tool name in params", 1.0, request_id)

    policy = get_policy(tool_name)
    if policy is None:
        decision = score_call(tool_name, ValidationResult(False, "UNKNOWN", "no policy"), 0.0)
        _log_decision(tool_name, decision.action, decision.risk_score, session_id)
        return _block_error(decision.explanation, decision.risk_score, request_id)

    structural = run_structural_validation(tool_name, arguments)
    judge = create_judge()
    semantic_band = await judge.classify(tool_name, arguments, context="")
    decision = score_call(tool_name, structural, semantic_band)
    _log_decision(tool_name, decision.action, decision.risk_score, session_id)

    if decision.action == "ALLOW":
        return await _forward_upstream(payload)

    if decision.action == "BLOCK":
        return _block_error(decision.explanation, decision.risk_score, request_id)

    pending_id = hitl_queue.store.add(
        {
            "tool_name": tool_name,
            "arguments": arguments,
            "risk_score": decision.risk_score,
            "explanation": decision.explanation,
            "session_id": session_id,
            "original_payload": payload,
        }
    )
    call = hitl_queue.store.get(pending_id)
    if call:
        await notify_escalation(call)

    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "status": "pending_review",
            "pending_id": pending_id,
            "risk_score": decision.risk_score,
            "explanation": decision.explanation,
        },
    }


def _serialize_call(call: hitl_queue.PendingCall) -> dict:
    return {
        "pending_id": call.pending_id,
        "tool_name": call.tool_name,
        "arguments": call.arguments,
        "risk_score": call.risk_score,
        "explanation": call.explanation,
        "status": call.status,
        "reviewer": call.reviewer,
        "session_id": call.session_id,
        "created_at": call.created_at.isoformat(),
        "updated_at": call.updated_at.isoformat(),
        "upstream_result": call.upstream_result,
    }


@app.get("/v1/pending")
async def list_pending() -> list[dict]:
    return [_serialize_call(c) for c in hitl_queue.store.list_all()]


@app.get("/v1/pending/{pending_id}")
async def get_pending(pending_id: str) -> dict:
    call = hitl_queue.store.get(pending_id)
    if call is None:
        raise HTTPException(status_code=404, detail="Pending call not found")
    return _serialize_call(call)


@app.post("/v1/pending/{pending_id}/approve")
async def approve_pending(pending_id: str, body: ReviewerBody) -> dict:
    call = hitl_queue.store.approve(pending_id, body.reviewer)
    if call is None:
        raise HTTPException(status_code=404, detail="Pending call not found")
    if call.status != "approved":
        raise HTTPException(status_code=400, detail="Call is not approvable")

    try:
        result = await _forward_upstream(call.original_payload)
        call.upstream_result = result
        return {"status": "approved", "pending_id": pending_id, "result": result}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Upstream forward failed: {exc}") from exc


@app.post("/v1/pending/{pending_id}/reject")
async def reject_pending(pending_id: str, body: ReviewerBody) -> dict:
    call = hitl_queue.store.reject(pending_id, body.reviewer)
    if call is None:
        raise HTTPException(status_code=404, detail="Pending call not found")
    return {"status": "rejected", "pending_id": pending_id}


if __name__ == "__main__":
    load_config()
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
