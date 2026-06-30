import pytest

from hitl.queue import PendingCallStore


@pytest.fixture
def store():
    return PendingCallStore()


def _sample_call():
    return {
        "tool_name": "send_payment",
        "arguments": {"amount": 150},
        "risk_score": 0.7,
        "explanation": "Escalated: amount exceeds threshold",
        "session_id": "sess-1",
        "original_payload": {"jsonrpc": "2.0", "method": "tools/call"},
    }


def test_add_creates_pending(store):
    pending_id = store.add(_sample_call())
    entry = store.get(pending_id)
    assert entry is not None
    assert entry.status == "pending"


def test_approve_records_reviewer(store):
    pending_id = store.add(_sample_call())
    entry = store.approve(pending_id, "alice")
    assert entry is not None
    assert entry.status == "approved"
    assert entry.reviewer == "alice"


def test_reject_records_reviewer(store):
    pending_id = store.add(_sample_call())
    entry = store.reject(pending_id, "bob")
    assert entry is not None
    assert entry.status == "rejected"
    assert entry.reviewer == "bob"


def test_list_pending_only_pending(store):
    id1 = store.add(_sample_call())
    id2 = store.add(_sample_call())
    store.approve(id1, "alice")
    pending = store.list_pending()
    assert len(pending) == 1
    assert pending[0].pending_id == id2
