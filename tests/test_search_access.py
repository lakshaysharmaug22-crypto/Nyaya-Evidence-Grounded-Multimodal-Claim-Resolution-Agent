import json

import pytest
from fastapi.testclient import TestClient

from agent import graph as G
from api import main
from api.store import Store, parse_query

c = TestClient(main.app)
BASE = {"damage_conf": 0.95, "amount_inr": 1499, "days_since_delivery": 2}


def post(cid, text, order, **kw):
    r = c.post("/claims/stream", json={"id": cid, "order_id": order, "text": text, **BASE, **kw})
    return [json.loads(x[6:]) for x in r.text.split("\n\n") if x.startswith("data: ")]


@pytest.fixture(scope="module", autouse=True)
def seeded():
    post("S-100", "box was crushed and the item is broken", "ORD7001")
    post("S-101", "wrong product delivered, different model", "ORD7002", damage_conf=0.2)
    post("S-102", "charger not included in the box", "ORD7003", damage_conf=0.2, customer_id="cust-zed")


def ids(q):
    return [h["id"] for h in c.get("/search", params={"q": q}).json()["hits"]]


# --- search
def test_parse_query_splits_filters_from_free_text():
    assert parse_query("wrong item decision:escalate type:damaged") == (["wrong", "item"], {"decision": "escalate", "claim_type": "damaged"})
    assert parse_query("http://x foo:bar") == (["http://x", "foo:bar"], {})

def test_exact_claim_id_ranks_first():
    assert ids("S-101")[0] == "S-101"

def test_order_id_prefix_search():
    assert "S-100" in ids("ORD700") and ids("ORD7002")[0] == "S-101"

def test_free_text_prefix_match():
    assert "S-100" in ids("crush") and "S-102" in ids("charger")

def test_multiple_words_are_anded():
    r = ids("box crushed")                       # both words required: S-102 has "box" but not "crushed"
    assert "S-100" in r and "S-102" not in r and "S-101" not in r

def test_filters_narrow_results():
    esc = c.get("/search", params={"q": "decision:escalate"}).json()["hits"]
    assert esc and all(h["decision"] == "escalate" for h in esc)
    assert "S-100" not in ids("decision:escalate") and "S-100" in ids("decision:approve")
    r = ids("box decision:escalate")
    assert "S-102" in r and "S-100" not in r

def test_customer_filter():
    assert ids("customer:cust-zed") == ["S-102"]

def test_empty_query_returns_recent_items():
    assert len(ids("")) >= 3

def test_hostile_query_does_not_break_search():
    for q in ['"', "\" OR 1=1 --", "*", "a AND", "NEAR(", "(", "col:", "\x00"]:
        assert c.get("/search", params={"q": q}).status_code == 200, q

def test_snippet_uses_markers_not_html():
    hit = next(h for h in c.get("/search", params={"q": "crush"}).json()["hits"] if h["id"] == "S-100")
    assert "\x01" in hit["snippet"] and "<" not in hit["snippet"]

def test_decisions_and_handoffs_are_searchable():
    c.post("/decisions", json={"id": "S-102", "action": "reject", "reason": "photo shows a different product"})
    c.post("/handoff", json={"id": "S-101", "note": "please call me about the swap"})
    kinds = {h["kind"] for h in c.get("/search", params={"q": "swap OR product"}).json()["hits"]}
    assert ids("kind:decision different") == ["S-102"] and ids("kind:handoff swap") == ["S-101"]

def test_rerun_replaces_index_entry():
    post("S-200", "first version crushed", "ORD8001")
    post("S-200", "second version dented", "ORD8001")
    assert "S-200" not in ids("crushed") and ids("dented") == ["S-200"]


# --- case detail
def test_case_detail_bundle():
    d = c.get("/cases/S-100").json()
    assert d["run"]["decision"] == "approve" and d["run"]["evidence"]["order_verified"] is True
    assert c.get("/cases/nope").status_code == 404


# --- customer tracking
def test_track_needs_both_ids_and_hides_which_is_wrong():
    ok = c.get("/track", params={"claim_id": "s-100", "order_id": "ord7001"})
    assert ok.status_code == 200 and ok.json()["status"] == "approved"
    wrong_order = c.get("/track", params={"claim_id": "S-100", "order_id": "ORD0000"})
    wrong_claim = c.get("/track", params={"claim_id": "S-999", "order_id": "ORD7001"})
    assert wrong_order.status_code == wrong_claim.status_code == 404 and wrong_order.json() == wrong_claim.json()

def test_track_statuses():
    assert c.get("/track", params={"claim_id": "S-102", "order_id": "ORD7003"}).json()["status"] == "under_review"
    c.post("/handoff", json={"id": "S-102", "note": "help"})
    assert c.get("/track", params={"claim_id": "S-102", "order_id": "ORD7003"}).json()["status"] == "with_a_person"

def test_track_leaks_no_internal_fields():
    body = c.get("/track", params={"claim_id": "S-100", "order_id": "ORD7001"}).json()
    assert set(body) == {"claim_id", "updated_at", "status", "message"}


# --- access control
def test_agent_endpoints_require_the_token_when_set(monkeypatch):
    monkeypatch.setattr(main, "AGENT_TOKEN", "s3cret")
    for path in ["/search?q=x", "/metrics", "/audit.csv", "/handoffs", "/overrides", "/drift", "/clusters", "/cases/S-100", "/recoverable"]:
        assert c.get(path).status_code == 401, path
        assert c.get(path, headers={"X-Agent-Token": "wrong"}).status_code == 401, path
        assert c.get(path, headers={"X-Agent-Token": "s3cret"}).status_code in (200, 404), path
    assert c.post("/decisions", json={"id": "x", "action": "approve"}).status_code == 401
    assert c.post("/replies", json={"id": "x", "text": "t"}).status_code == 401
    assert c.post("/claims/x/resume").status_code == 401

def test_customer_endpoints_stay_public_when_token_set(monkeypatch):
    monkeypatch.setattr(main, "AGENT_TOKEN", "s3cret")
    assert c.get("/health").status_code == 200
    assert c.get("/track", params={"claim_id": "S-100", "order_id": "ORD7001"}).status_code == 200
    assert c.post("/handoff", json={"id": "S-100", "note": "hi"}).status_code == 200
    assert post("S-300", "box was crushed", "ORD9001")[-1]["final"]["decision"] == "approve"

def test_rate_limit(monkeypatch):
    monkeypatch.setattr(main, "RATE_PER_MIN", 3)
    main._hits.clear()
    codes = [c.get("/track", params={"claim_id": "a", "order_id": "b"}).status_code for _ in range(5)]
    assert codes == [404, 404, 404, 429, 429]
    main._hits.clear()


# --- durability through the API
def test_crashed_run_is_reported_and_can_be_resumed():
    G.CRASH_BEFORE_ACT.add("R-1")
    ev = post("R-1", "box was crushed", "ORD5001")
    assert ev[-1]["resumable"] is True and "final" not in ev[-1]
    assert {"id": "R-1", "next": ["n_act"]} in c.get("/recoverable").json()
    assert "unfinished" in post("R-1", "box was crushed", "ORD5001")[-1]["error"]     # can't start a second run on top
    r = c.post("/claims/R-1/resume").json()
    assert r["resumed"] and r["final"]["decision"] == "approve" and r["verified"]
    assert all(x["id"] != "R-1" for x in c.get("/recoverable").json())
    assert c.post("/claims/R-1/resume").json()["resumed"] is False
    assert ids("R-1")[0] == "R-1"                                                     # resumed run is searchable

def test_uploads_are_kept_out_of_graph_state(png_b64):
    post("B-1", "box was crushed", "ORD5002", image_b64=png_b64())
    claim = main.graph.get_state(main._cfg("B-1")).values["claim"]
    assert "image_b64" not in claim and claim["image_ref"].endswith("B-1.image")

def test_data_survives_a_restart():
    fresh = Store(str(main.DATA / "app.db"))                      # what a new process would open
    assert any(r["id"] == "S-100" for r in fresh.load("run"))
    assert [h["id"] for h in fresh.search("ORD7002")][0] == "S-101"
