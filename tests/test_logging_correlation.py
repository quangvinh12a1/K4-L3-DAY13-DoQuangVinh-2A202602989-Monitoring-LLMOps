from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import httpx

from app import logging_config
from app.main import app

CHAT_BODY = {
    "user_id": "student-01",
    "session_id": "session-01",
    "feature": "qa",
    "message": "My email is student@vinuni.edu.vn and card 4111 1111 1111 1111",
}


def _post_chat(headers: dict[str, str] | None = None) -> httpx.Response:
    async def send() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post("/chat", json=CHAT_BODY, headers=headers or {})

    return asyncio.run(send())


def _events(log_path: Path) -> list[dict]:
    return [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]


def test_generates_correlation_id_and_response_headers(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(logging_config, "LOG_PATH", tmp_path / "logs.jsonl")
    response = _post_chat()

    correlation_id = response.headers["x-request-id"]
    assert re.fullmatch(r"req-[0-9a-f]{8}", correlation_id)
    assert float(response.headers["x-response-time-ms"]) >= 0
    assert response.json()["correlation_id"] == correlation_id


def test_reuses_valid_incoming_request_id_and_rejects_unsafe_one(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(logging_config, "LOG_PATH", tmp_path / "logs.jsonl")
    assert _post_chat({"x-request-id": "req-abc12345"}).headers["x-request-id"] == "req-abc12345"

    unsafe = _post_chat({"x-request-id": "bad id\ninjected"}).headers["x-request-id"]
    assert re.fullmatch(r"req-[0-9a-f]{8}", unsafe)


def test_failed_request_returns_and_logs_correlation_id(monkeypatch, tmp_path: Path) -> None:
    from app.incidents import STATE

    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)
    monkeypatch.setitem(STATE, "tool_fail", True)
    response = _post_chat()

    assert response.status_code == 500
    correlation_id = response.json()["correlation_id"]
    assert correlation_id == response.headers["x-request-id"]
    failed = next(e for e in _events(log_path) if e["event"] == "request_failed")
    assert failed["correlation_id"] == correlation_id
    assert failed["tool_success"] is False
    assert "student@vinuni.edu.vn" not in json.dumps(failed)


def test_api_logs_are_enriched_scrubbed_and_not_leaking_between_requests(monkeypatch, tmp_path: Path) -> None:
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)
    first = _post_chat().headers["x-request-id"]
    second = _post_chat().headers["x-request-id"]
    assert first != second

    api_events = [e for e in _events(log_path) if e.get("service") == "api"]
    assert {e["correlation_id"] for e in api_events} == {first, second}
    for event in api_events:
        for field in ("user_id_hash", "session_id", "feature", "model", "env"):
            assert event.get(field), f"{event['event']} missing {field}"
        assert "student-01" not in json.dumps(event)

    raw = log_path.read_text(encoding="utf-8")
    assert "student@vinuni.edu.vn" not in raw
    assert "4111 1111 1111 1111" not in raw
    assert "REDACTED_EMAIL" in raw and "REDACTED_CREDIT_CARD" in raw
