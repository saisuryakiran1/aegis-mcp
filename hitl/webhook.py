from __future__ import annotations

import logging

import httpx

from config import get_config
from hitl.queue import PendingCall

logger = logging.getLogger(__name__)


async def notify_escalation(call: PendingCall) -> None:
    cfg = get_config()
    webhook_url = cfg.hitl.webhook_url
    if not webhook_url:
        logger.info("HITL webhook URL not configured; skipping notification for %s", call.pending_id)
        return

    review_url = f"{cfg.hitl.review_base_url.rstrip('/')}/v1/pending/{call.pending_id}"
    payload = {
        "tool_name": call.tool_name,
        "arguments": call.arguments,
        "risk_score": call.risk_score,
        "explanation": call.explanation,
        "pending_id": call.pending_id,
        "review_url": review_url,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(webhook_url, json=payload)
            response.raise_for_status()
            logger.info("HITL webhook notified for pending_id=%s", call.pending_id)
    except Exception as exc:
        logger.warning("HITL webhook notification failed for %s: %s", call.pending_id, exc)
