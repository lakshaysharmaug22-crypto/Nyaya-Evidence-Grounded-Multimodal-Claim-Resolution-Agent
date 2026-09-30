"""FastAPI app: claim streaming, durable runs, agent console endpoints, search, and customer tracking.

Access model
- Public (customers): /claims/stream, /photo/check, /voice/transcribe, /handoff, /track
- Agent-only: everything else. Set AGENT_TOKEN and send it as the X-Agent-Token header. If AGENT_TOKEN is unset
  the API is open, which is fine for a local demo and NOT for a real deployment.
"""
import asyncio
import base64
import csv
import hmac
import io
import json
import os
import sqlite3
import sys
import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, StreamingResponse
from langgraph.checkpoint.sqlite import SqliteSaver
from PIL import Image

from agent import blobs, drift, feedback, history, llm, reply, tools
from agent import graph as G
from agent.metrics import RunMetrics
from ml import predict, voice
from ml.quality_gate import check as quality_check
from agent.guard import looks_like_injection

from .store import Store

DATA = Path(os.getenv("DATA_DIR", "data"))
DATA.mkdir(parents=True, exist_ok=True)
AGENT_TOKEN = os.getenv("AGENT_TOKEN")
RATE_PER_MIN = int(os.getenv("RATE_LIMIT_PER_MIN", "30"))

app = FastAPI(title="Nyaya: Evidence-Grounded Multimodal Claim Resolution Agent")
ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",")]
app.add_middleware(CORSMiddleware, allow_origins=ORIGINS, allow_methods=["*"], allow_headers=["*"])

if os.getenv("USE_MCP") == "1":                    # route the agent's tools through the MCP server
    from agent import mcp_client
    mcp_client.register_from_stdio(sys.executable, ["-m", "mcp_servers.support_tools"])

tools.use_sqlite(str(DATA / "idempotency.db"))     # a restarted process never repeats a refund
_cp = SqliteSaver(sqlite3.connect(str(DATA / "checkpoints.db"), check_same_thread=False))
graph = G.build(_cp)                               # durable state: crashed runs can be resumed
_llm = llm.get_llm()
G.set_reader(llm.Reader(_llm) if _llm else None)   # None -> deterministic briefs, no model calls

store = Store(str(DATA / "app.db"))
RUNS: list[dict] = store.load("run")               # in-memory views, rebuilt from SQLite on startup
DECISIONS: list[dict] = store.load("decision")
HANDOFFS: list[dict] = store.load("handoff")
REPLIES: list[dict] = store.load("reply")

PARALLEL = ["photo", "invoice", "order", "classify"]
SERIAL = ["fuse", "act", "verify"]


def require_agent(x_agent_token: str | None = Header(default=None)):
    if AGENT_TOKEN and not hmac.compare_digest(x_agent_token or "", AGENT_TOKEN):
        raise HTTPException(401, "agent access required")


_hits: dict[str, deque] = defaultdict(deque)


def rate_limit(request: Request):
    ip = request.client.host if request.client else "?"
    now, q = time.time(), _hits[ip]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= RATE_PER_MIN:
        raise HTTPException(429, "too many requests, slow down")
    q.append(now)


def _sse(obj) -> str:
    return f"data: {json.dumps(obj)}\n\n"


def _cfg(cid: str) -> dict:
    return {"configurable": {"thread_id": cid}}


def _record(cid: str, claim: dict, out: dict, ms: float) -> dict:
    """Store a finished run (memory + SQLite + search index) and build the payload the UI receives."""
    history.record(claim.get("customer_id"))
    trace = tools.EVENTS.get(cid, [])
    ev = out.get("evidence") or {}
    amount = (out.get("invoice") or {}).get("amount_inr")
    b = out.get("brief")
    run = {"id": cid, "ts": time.time(), "order_id": claim.get("order_id"), "customer_id": claim.get("customer_id"),
           "decision": out["decision"]["decision"], "rule": out["decision"]["rule"], "lane": out["decision"]["lane"],
           "ms": ms, "verified": out["verified"], "recovered": any(not e["ok"] for e in trace),
           "claim_type": ev.get("claim_type"), "cluster": (out.get("kind") or {}).get("cluster"),
           "est_refund_inr": ev.get("est_refund_inr"), "amount_inr": amount, "trace": trace,
           "text": claim.get("text", ""), "evidence": ev, "draft_reply": reply.draft(out["decision"], amount, cid),
           "routed_llm": b is not None, "llm_used": bool(b and b["llm_used"]), "cost_inr": (b or {}).get("cost_inr", 0.0),
           "in_tokens": (b or {}).get("in_tokens", 0), "out_tokens": (b or {}).get("out_tokens", 0),
           "groundedness": (b or {}).get("groundedness"), "brief": (b or {}).get("brief")}
    RUNS.append(run)
    store.save("run", run)
    store.index("claim", cid, id=cid, order_id=run["order_id"], customer_id=run["customer_id"], text=run["text"],
                decision=run["decision"], rule=run["rule"], lane=run["lane"], claim_type=run["claim_type"], ts=run["ts"])
    return {"final": out["decision"], "verified": out["verified"], "ms": ms, "trace": trace, "evidence": ev,
            "draft_reply": run["draft_reply"], "brief": b}


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/claims/stream", dependencies=[Depends(rate_limit)])
async def stream(claim: dict):
    claim = dict(claim)
    cid = str(claim.setdefault("id", "anon"))
    for kind, key in (("image", "image_b64"), ("invoice", "invoice_b64")):     # keep big uploads out of graph state
        if claim.get(key):
            claim[f"{kind}_ref"] = blobs.put(cid, kind, claim.pop(key))

    async def gen():
        m = RunMetrics()
        if _cp and (await asyncio.to_thread(graph.get_state, _cfg(cid))).next:
            yield _sse({"error": "this claim has an unfinished run; resume it instead", "resumable": True, "id": cid})
            return
        for n in PARALLEL:
            yield _sse({"node": n, "status": "running"})
        await asyncio.sleep(0.4)
        for n in PARALLEL:
            with m.node(n):
                pass
            yield _sse({"node": n, "status": "done"})
        for n in SERIAL:
            yield _sse({"node": n, "status": "running"})
            await asyncio.sleep(0.3)
            with m.node(n):
                pass
            yield _sse({"node": n, "status": "done"})
        if claim.get("inject_failure"):            # demo: order lookup fails once, retry recovers
            tools.FAIL_ONCE.add(f"order_lookup:{cid}")
        t0 = time.perf_counter()
        try:
            out = await asyncio.to_thread(graph.invoke, {"claim": claim}, _cfg(cid))
        except Exception as e:                      # state up to the last finished step is saved
            yield _sse({"error": f"{type(e).__name__}: {e}", "resumable": True, "id": cid})
            return
        yield _sse(_record(cid, claim, out, round((time.perf_counter() - t0) * 1000, 2)) | {"final_event": True})
    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/recoverable", dependencies=[Depends(require_agent)])
def recoverable():
    """Runs that stopped mid-way (crash, restart) and can be resumed."""
    ids = [r[0] for r in _cp.conn.execute("select distinct thread_id from checkpoints limit 500").fetchall()]
    out = []
    for i in ids:
        st = graph.get_state(_cfg(i))
        if st.next:
            out.append({"id": i, "next": list(st.next)})
    return out


@app.post("/claims/{claim_id}/resume", dependencies=[Depends(require_agent)])
async def resume(claim_id: str):
    st = await asyncio.to_thread(graph.get_state, _cfg(claim_id))
    if not st.next:
        return {"resumed": False, "reason": "nothing pending"}
    claim = st.values["claim"]
    t0 = time.perf_counter()
    try:
        out = await asyncio.to_thread(graph.invoke, None, _cfg(claim_id))
    except Exception as e:
        raise HTTPException(500, f"resume failed: {type(e).__name__}: {e}")
    return {"resumed": True, **_record(claim_id, claim, out, round((time.perf_counter() - t0) * 1000, 2))}


@app.post("/photo/check", dependencies=[Depends(rate_limit)])
def photo_check(body: dict):
    img = Image.open(io.BytesIO(base64.b64decode(body["image_b64"])))
    return quality_check(img)


@app.post("/voice/transcribe", dependencies=[Depends(rate_limit)])
def transcribe(body: dict):
    audio_b64 = body.get("audio_b64")
    if not isinstance(audio_b64, str) or not audio_b64:
        raise HTTPException(400, "audio_b64 is required")
    if len(audio_b64) > 14_000_000:
        raise HTTPException(413, "audio is too large")
    result = voice.transcribe(audio_b64)
    if result.get("ok"):
        result["injection_flagged"] = looks_like_injection(result["text"])
    return result


@app.post("/decisions", dependencies=[Depends(require_agent)])
def decide(body: dict):
    """Human approve/reject. Rejections require a reason; they feed the eval/override set."""
    if body.get("action") not in ("approve", "reject"):
        raise HTTPException(400, "action must be approve or reject")
    if body["action"] == "reject" and not str(body.get("reason", "")).strip():
        raise HTTPException(400, "reject needs a reason")
    rec = {"id": body["id"], "action": body["action"], "reason": body.get("reason", ""), "ts": time.time()}
    DECISIONS.append(rec)
    store.save("decision", rec)
    store.index("decision", f"{rec['id']}:{rec['ts']}", id=rec["id"], text=rec["reason"], decision=rec["action"], ts=rec["ts"])
    return rec


@app.post("/decisions/batch", dependencies=[Depends(require_agent)])
def decide_batch(body: dict):
    recs = [{"id": i, "action": "approve", "reason": "", "ts": time.time(), "batch": True} for i in body.get("ids", [])]
    for r in recs:
        DECISIONS.append(r)
        store.save("decision", r)
        store.index("decision", f"{r['id']}:{r['ts']}", id=r["id"], decision="approve", ts=r["ts"])
    return {"approved": len(recs)}


@app.get("/overrides", dependencies=[Depends(require_agent)])
def overrides():
    return [d for d in DECISIONS if d["action"] == "reject"]


@app.get("/learning-queue", dependencies=[Depends(require_agent)])
def learning_queue():
    """Human-labeled disagreements for review before any model retraining."""
    return feedback.learning_queue(RUNS, DECISIONS)


@app.post("/handoff", dependencies=[Depends(rate_limit)])
def handoff(body: dict):
    """Customer asks for a person. The full case (text, decision so far, trace) goes with it."""
    run = next((r for r in reversed(RUNS) if r["id"] == body.get("id")), None)
    rec = {"id": body.get("id"), "note": body.get("note", ""), "ts": time.time(), "case": run}
    HANDOFFS.append(rec)
    store.save("handoff", rec)
    store.index("handoff", f"{rec['id']}:{rec['ts']}", id=str(rec["id"]), order_id=(run or {}).get("order_id"),
                text=rec["note"], decision=(run or {}).get("decision"), ts=rec["ts"])
    return {"queued": True, "position": len(HANDOFFS), "has_case": run is not None}


@app.get("/handoffs", dependencies=[Depends(require_agent)])
def handoffs():
    return HANDOFFS


@app.post("/replies", dependencies=[Depends(require_agent)])
def send_reply(body: dict):
    """Logs the reply the agent approved. Delivery (email / WhatsApp / SMS) is not wired up yet."""
    rec = {"id": body["id"], "text": body["text"], "ts": time.time(), "delivered": False}
    REPLIES.append(rec)
    store.save("reply", rec)
    return rec


_AUDIT_COLS = ["id", "ts", "decision", "rule", "lane", "ms", "verified", "recovered", "claim_type", "cluster",
               "amount_inr", "est_refund_inr", "routed_llm", "llm_used", "cost_inr", "trace"]


def _csv(runs) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=_AUDIT_COLS, extrasaction="ignore")
    w.writeheader()
    for r in runs:
        w.writerow({**r, "trace": json.dumps(r["trace"])})
    return buf.getvalue()


@app.get("/audit.csv", response_class=PlainTextResponse, dependencies=[Depends(require_agent)])
def audit_all():
    return _csv(RUNS)


@app.get("/audit/{claim_id}.csv", response_class=PlainTextResponse, dependencies=[Depends(require_agent)])
def audit_one(claim_id: str):
    rows = [r for r in RUNS if r["id"] == claim_id]
    if not rows:
        raise HTTPException(404, "unknown claim")
    return _csv(rows)


@app.get("/search", dependencies=[Depends(require_agent)])
def search(q: str = "", limit: int = 20):
    """Agent search across claims, handoffs and human decisions.
    Free text matches id, order, customer and claim text (prefix match). Filters: decision:, rule:, lane:, type:, kind:, order:, customer:"""
    return {"q": q, "hits": store.search(q, min(max(limit, 1), 50))}


@app.get("/cases/{claim_id}", dependencies=[Depends(require_agent)])
def case(claim_id: str):
    run = next((r for r in reversed(RUNS) if r["id"] == claim_id), None)
    if not run:
        raise HTTPException(404, "unknown claim")
    return {"run": run, "decisions": [d for d in DECISIONS if d["id"] == claim_id],
            "replies": [r for r in REPLIES if r["id"] == claim_id], "handoffs": [h["note"] for h in HANDOFFS if h["id"] == claim_id]}


def _customer_status(run: dict, handed_off: bool) -> dict:
    if handed_off:
        return {"status": "with_a_person", "message": "A team member has your case and will update you soon."}
    if run["decision"] == "approve":
        return {"status": "approved", "message": "Approved. Your refund is on its way (5-7 working days)."}
    if run["rule"] == "outside_window":
        return {"status": "not_eligible", "message": "This claim is outside the 7-day window. Reply or ask for a person if you disagree."}
    if run["rule"] == "order_not_found":
        return {"status": "needs_info", "message": "We couldn't match an order. Please share your order ID or invoice."}
    return {"status": "under_review", "message": "A team member is reviewing your claim."}


@app.get("/track", dependencies=[Depends(rate_limit)])
def track(claim_id: str, order_id: str):
    """Customer lookup. Needs BOTH the claim ID and the order ID, and never says which one was wrong."""
    run = next((r for r in reversed(RUNS) if r["id"].lower() == claim_id.strip().lower()
                and (r.get("order_id") or "").lower() == order_id.strip().lower()), None)
    if not run:
        raise HTTPException(404, "We couldn't find a claim with those details.")
    handed = any(h["id"] == run["id"] for h in HANDOFFS)
    return {"claim_id": run["id"], "updated_at": run["ts"], **_customer_status(run, handed)}


@app.get("/metrics", dependencies=[Depends(require_agent)])
def metrics():
    n = len(RUNS)
    if not n:
        return {"n": 0}
    lat = sorted(r["ms"] for r in RUNS)
    by = {}
    for r in RUNS:
        by[r["decision"]] = by.get(r["decision"], 0) + 1
    g = [r["groundedness"] for r in RUNS if r.get("groundedness") is not None]
    queue = feedback.learning_queue(RUNS, DECISIONS)
    return {"n": n, "learning_queue": len(queue),
            "auto_resolve_rate": round(sum(r["lane"] == "ready" for r in RUNS) / n, 3),
            "verified_rate": round(sum(r["verified"] for r in RUNS) / n, 3),
            "p95_ms": lat[int(0.95 * (n - 1))], "recovered": sum(r["recovered"] for r in RUNS), "decisions": by,
            "overrides": sum(d["action"] == "reject" for d in DECISIONS), "handoffs": len(HANDOFFS),
            "llm_routed_rate": round(sum(r.get("routed_llm", False) for r in RUNS) / n, 3),
            "llm_used_rate": round(sum(r.get("llm_used", False) for r in RUNS) / n, 3),
            "avg_cost_inr": round(sum(r.get("cost_inr", 0) for r in RUNS) / n, 4),
            "total_cost_inr": round(sum(r.get("cost_inr", 0) for r in RUNS), 4),
            "groundedness": round(sum(g) / len(g), 3) if g else None}


@app.get("/drift", dependencies=[Depends(require_agent)])
def drift_status():
    return drift.check(RUNS)


@app.get("/clusters", dependencies=[Depends(require_agent)])
def clusters():
    """Escalated/rejected runs grouped by the text cluster, labelled by top terms."""
    terms = predict.cluster_terms()
    counts: dict[int, int] = {}
    for r in RUNS:
        if r["decision"] != "approve" and r.get("cluster") is not None:
            counts[r["cluster"]] = counts.get(r["cluster"], 0) + 1
    return [{"cluster": c, "terms": terms.get(c, []), "count": n} for c, n in sorted(counts.items(), key=lambda x: -x[1])]
