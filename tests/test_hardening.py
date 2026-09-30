import base64
import dataclasses
import json

import pytest
from fastapi.testclient import TestClient

from agent import delivery
from api import config, main

c = TestClient(main.app)


def final(r):
    evs = [json.loads(x[6:]) for x in r.text.split("\n\n") if x.startswith("data: ")]
    return evs[-1]


# --- configuration
def test_production_refuses_unsafe_settings(monkeypatch):
    monkeypatch.setenv("NYAYA_ENV", "production")
    monkeypatch.delenv("AGENT_TOKEN", raising=False)
    monkeypatch.setenv("ALLOWED_ORIGINS", "*")
    with pytest.raises(RuntimeError, match="AGENT_TOKEN.*ALLOWED_ORIGINS"):
        config.load()


def test_production_accepts_safe_settings_and_locks_overrides(monkeypatch):
    monkeypatch.setenv("NYAYA_ENV", "production")
    monkeypatch.setenv("AGENT_TOKEN", "x" * 24)
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://nyaya.vercel.app")
    monkeypatch.delenv("ALLOW_SCORE_OVERRIDES", raising=False)
    s = config.load()
    assert s.production and not s.allow_score_overrides and s.log_json


def test_bad_numeric_env_is_a_clear_error(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_MIN", "lots")
    with pytest.raises(ValueError, match="RATE_LIMIT_PER_MIN"):
        config.load()


# --- trust boundary
def test_public_caller_cannot_self_score_a_claim(monkeypatch):
    monkeypatch.setattr(main, "AGENT_TOKEN", "t" * 20)
    monkeypatch.setattr(main, "CFG", dataclasses.replace(main.CFG, allow_score_overrides=False))
    body = {"id": "H-SELF", "order_id": "ORD55", "damage_conf": 0.99, "amount_inr": 999, "days_since_delivery": 1}
    assert final(c.post("/claims/stream", json=body))["final"]["decision"] != "approve"
    agent = final(c.post("/claims/stream", json=body | {"id": "H-AGENT"}, headers={"X-Agent-Token": "t" * 20}))
    assert agent["final"]["decision"] == "approve"


@pytest.mark.parametrize("body,msg", [
    ({"id": "../../etc", "order_id": "ORD1"}, "id must be"),
    ({"id": "H1", "order_id": "ORD1", "damage_conf": 3}, "damage_conf"),
    ({"id": "H1", "order_id": "ORD1", "amount_inr": "lots"}, "amount_inr"),
    ({"id": "H1", "order_id": "ORD1", "text": "x" * 5000}, "longer than"),
    ({"id": "H1", "order_id": "ORD1", "image_b64": "not base64!!"}, "base64"),
])
def test_claim_validation(body, msg):
    r = c.post("/claims/stream", json=body)
    assert r.status_code == 422 and msg in r.json()["detail"]


def test_unreadable_photo_is_422_not_500():
    r = c.post("/photo/check", json={"image_b64": base64.b64encode(b"not an image").decode()})
    assert r.status_code == 422


def test_oversized_body_is_rejected_before_parsing(monkeypatch):
    monkeypatch.setattr(main, "MAX_BODY", 1000)
    r = c.post("/claims/stream", content=b"{" + b" " * 2000 + b"}", headers={"content-type": "application/json"})
    assert r.status_code == 413


def test_security_headers_and_request_id():
    r = c.get("/health", headers={"X-Request-Id": "abc-123"})
    assert r.headers["x-request-id"] == "abc-123"
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"
    assert len(c.get("/health", headers={"X-Request-Id": "<script>"}).headers["x-request-id"]) == 16


def test_ready_reports_components():
    r = c.get("/ready").json()
    assert r["ok"] and r["reply_mode"] == "dry_run" and set(r) >= {"llm", "cnn", "auth"}


# --- reply delivery
@pytest.fixture(autouse=True)
def _clean_delivery(monkeypatch):
    delivery._sent.clear()
    for k in ("REPLY_MODE", "REPLY_ALLOWLIST", "REPLY_WEBHOOK_URL", "REPLY_WEBHOOK_SECRET"):
        monkeypatch.delenv(k, raising=False)


def test_default_is_dry_run_even_when_approved():
    r = c.post("/replies", json={"id": "D1", "text": "hi", "to": "a@b.com", "approved": True}).json()
    assert r["status"] == "dry_run" and r["delivered"] is False


def test_unapproved_reply_is_never_sent(monkeypatch):
    monkeypatch.setenv("REPLY_MODE", "webhook")
    monkeypatch.setenv("REPLY_ALLOWLIST", "a@b.com")
    assert c.post("/replies", json={"id": "D2", "text": "hi", "to": "a@b.com"}).json()["status"] == "not_approved"


def test_destination_must_be_allowlisted(monkeypatch):
    monkeypatch.setenv("REPLY_MODE", "webhook")
    monkeypatch.setenv("REPLY_ALLOWLIST", "@example.com")
    r = c.post("/replies", json={"id": "D3", "text": "hi", "to": "someone@gmail.com", "approved": True}).json()
    assert r["status"] == "destination_not_allowed"
    assert delivery.allowed("ops@example.com") and not delivery.allowed("ops@example.com.evil.io")


def test_webhook_sends_once_with_signature(monkeypatch):
    sent = []

    class Resp:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake_urlopen(req, timeout):
        sent.append((req.full_url, req.headers, json.loads(req.data)))
        return Resp()

    monkeypatch.setattr(delivery.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("REPLY_MODE", "webhook")
    monkeypatch.setenv("REPLY_WEBHOOK_URL", "https://hooks.example.com/nyaya")
    monkeypatch.setenv("REPLY_WEBHOOK_SECRET", "shh")
    monkeypatch.setenv("REPLY_ALLOWLIST", "+919999999999")
    body = {"id": "D4", "reply_id": "D4-r1", "text": "Refund issued", "to": "+919999999999", "approved": True}
    first, again = c.post("/replies", json=body).json(), c.post("/replies", json=body).json()
    assert first["status"] == "sent" and again["duplicate"] is True and len(sent) == 1
    url, headers, payload = sent[0]
    assert payload == {"claim_id": "D4", "to": "+919999999999", "text": "Refund issued"}
    assert "X-nyaya-signature" in headers


def test_webhook_failure_is_reported_not_faked(monkeypatch):
    def boom(req, timeout):
        raise OSError("connection refused")
    monkeypatch.setattr(delivery.urllib.request, "urlopen", boom)
    monkeypatch.setenv("REPLY_MODE", "webhook")
    monkeypatch.setenv("REPLY_WEBHOOK_URL", "https://hooks.example.com/nyaya")
    monkeypatch.setenv("REPLY_ALLOWLIST", "a@b.com")
    r = c.post("/replies", json={"id": "D5", "text": "hi", "to": "a@b.com", "approved": True}).json()
    assert r["status"] == "failed" and r["delivered"] is False


def test_plain_http_webhook_is_refused(monkeypatch):
    monkeypatch.setenv("REPLY_MODE", "webhook")
    monkeypatch.setenv("REPLY_WEBHOOK_URL", "http://insecure.example.com")
    monkeypatch.setenv("REPLY_ALLOWLIST", "a@b.com")
    r = c.post("/replies", json={"id": "D6", "text": "hi", "to": "a@b.com", "approved": True}).json()
    assert r["status"] == "failed" and "https" in r["error"]
