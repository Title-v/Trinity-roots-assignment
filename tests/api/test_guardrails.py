"""GUARD-01 through GUARD-03: inspect outbound model data and backend limits."""

import json
import stat

from sqlalchemy import select
from sqlalchemy.orm import Session

import assistant
import assistant_privacy
from models import AssistantAuditLog


def test_guard_01_masks_all_sensitive_values_before_model_request(
    owner, model_http, payload
):
    day = payload["slots"][0]["starts_at"][:10]
    values = ["1234567890123", "0812345678", "demo@example.com", "sk-proj-" + "x" * 24]
    message = f"Find a room on {day} from 14:00 to 16:00 for 5 people. " + " ".join(
        values
    )
    model_http.reply("clarify_room_search", {"reason": "equipment_needed"})
    response = owner.post(
        "/assistant/chat", json={"messages": [{"role": "user", "content": message}]}
    )
    assert response.status_code == 200
    sent = model_http.calls[0]["input"][0]["content"]
    assert all(value not in sent for value in values)
    assert sent.count("[REDACTED]") == 4
    assert all(detail in sent for detail in [day, "14:00", "16:00", "5 people"])


def test_guard_02_exact_audit_bodies_are_correlated_and_private(
    owner, model_http, db, monkeypatch
):
    original = "Find a room. Email: synthetic@example.com"
    model_http.reply("clarify_room_search", {"reason": "both"})
    response = owner.post(
        "/assistant/chat", json={"messages": [{"role": "user", "content": original}]}
    )
    assert response.status_code == 200
    path = assistant_privacy.AUDIT_PATH
    entries = [json.loads(line) for line in path.read_text().splitlines()]
    assert [entry["event"] for entry in entries] == ["request", "response"]
    assert entries[0]["request_id"] == entries[1]["request_id"]
    assert entries[0]["body"] == model_http.requests[0]
    assert entries[1]["body"] == model_http.responses[0]
    assert all(entry["time"] and "headers" not in entry for entry in entries)
    assert "synthetic@example.com" not in entries[0]["body"]
    assert "sk-test-not-a-real-key" not in path.read_text()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600

    # Production uses durable private database rows instead of a local JSONL file.
    monkeypatch.setenv("ASSISTANT_AUDIT_BACKEND", "database")
    model_http.reply("clarify_room_search", {"reason": "both"})
    response = owner.post(
        "/assistant/chat", json={"messages": [{"role": "user", "content": original}]}
    )
    assert response.status_code == 200
    with Session(db) as session:
        rows = session.scalars(
            select(AssistantAuditLog).order_by(AssistantAuditLog.id)
        ).all()
        assert [row.event for row in rows] == ["request", "response"]
        assert rows[0].request_id == rows[1].request_id
        assert rows[0].body == model_http.requests[-1]
        assert rows[1].body == model_http.responses[-1]
        assert rows[1].status == 200
        assert all(row.created_at is not None for row in rows)
    assert len(path.read_text().splitlines()) == 2


def test_guard_03_shared_quota_is_per_account_and_expires(
    owner, other, payload, model_http, monkeypatch
):
    clock = [100.0]
    monkeypatch.setattr(assistant, "monotonic", lambda: clock[0])
    for _ in range(9):
        assert owner.post("/assistant/alternatives", json=payload).status_code == 200
    model_http.reply("clarify_room_search", {"reason": "people"})
    message = {"messages": [{"role": "user", "content": "Find a room"}]}
    assert owner.post("/assistant/chat", json=message).status_code == 200
    limited = owner.post("/assistant/alternatives", json=payload)
    assert limited.status_code == 429 and limited.headers["Retry-After"] == "60"
    model_http.reply("clarify_room_search", {"reason": "people"})
    assert other.post("/assistant/chat", json=message).status_code == 200
    clock[0] += 60
    assert owner.post("/assistant/alternatives", json=payload).status_code == 200
    assert len(model_http.calls) == 2
