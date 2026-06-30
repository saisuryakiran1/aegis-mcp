from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class PendingCall:
    pending_id: str
    tool_name: str
    arguments: dict
    risk_score: float
    explanation: str
    status: str
    session_id: str
    original_payload: dict
    reviewer: str | None = None
    upstream_result: Any | None = None
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)


class PendingCallStore:
    def __init__(self) -> None:
        self._store: dict[str, PendingCall] = {}

    def add(self, call: dict) -> str:
        pending_id = str(uuid.uuid4())
        entry = PendingCall(
            pending_id=pending_id,
            tool_name=call["tool_name"],
            arguments=call["arguments"],
            risk_score=call["risk_score"],
            explanation=call["explanation"],
            status="pending",
            session_id=call.get("session_id", ""),
            original_payload=call["original_payload"],
        )
        self._store[pending_id] = entry
        return pending_id

    def get(self, pending_id: str) -> PendingCall | None:
        return self._store.get(pending_id)

    def approve(self, pending_id: str, reviewer: str) -> PendingCall | None:
        entry = self._store.get(pending_id)
        if entry is None:
            return None
        entry.status = "approved"
        entry.reviewer = reviewer
        entry.updated_at = _utcnow()
        return entry

    def reject(self, pending_id: str, reviewer: str) -> PendingCall | None:
        entry = self._store.get(pending_id)
        if entry is None:
            return None
        entry.status = "rejected"
        entry.reviewer = reviewer
        entry.updated_at = _utcnow()
        return entry

    def list_pending(self) -> list[PendingCall]:
        return [c for c in self._store.values() if c.status == "pending"]

    def list_all(self) -> list[PendingCall]:
        return sorted(self._store.values(), key=lambda c: c.updated_at, reverse=True)


store = PendingCallStore()
