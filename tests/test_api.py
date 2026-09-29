import json
from fastapi.testclient import TestClient
from api.main import app

c = TestClient(app)


def events(resp):
    return [json.loads(x[6:]) for x in resp.text.split("\n\n") if x.startswith("data: ")]


def test_health():
    assert c.get("/health").json() == {"ok": True}

def test_stream_emits_all_nodes_then_final():
    ev = events(c.post("/claims/stream", json={"id": "A1", "order_id": "ORD1", "damage_conf": 0.95, "amount_inr": 999, "days_since_delivery": 1}))
    nodes = {e["node"] for e in ev if "node" in e}
    assert nodes == {"photo", "invoice", "order", "classify", "fuse", "act", "verify"}
    assert ev[-1]["final"]["decision"] == "approve"

def test_photo_check_endpoint(png_b64):
    assert c.post("/photo/check", json={"image_b64": png_b64()}).json()["ok"] is True
    assert c.post("/photo/check", json={"image_b64": png_b64(blur=8)}).json()["reason"] == "blurry"

def test_metrics_after_runs():
    c.post("/claims/stream", json={"id": "A2", "order_id": "ORD2", "damage_conf": 0.95, "amount_inr": 999, "days_since_delivery": 1, "inject_failure": True})
    m = c.get("/metrics").json()
    assert m["n"] >= 1 and m["recovered"] >= 1
