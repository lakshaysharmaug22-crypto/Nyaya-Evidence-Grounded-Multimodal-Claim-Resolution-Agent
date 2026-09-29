"""FastAPI app: SSE claim streaming plus the console, insights and audit endpoints."""
import asyncio
import base64
import csv
import io
import json
import os
import sys
import time

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, StreamingResponse
from PIL import Image

from agent import drift, history, reply, tools
from agent.graph import build
from agent.metrics import RunMetrics
from ml import predict, voice
from ml.quality_gate import check as quality_check

app = FastAPI(title="Support Resolution Agent")
ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",")]
app.add_middleware(CORSMiddleware, allow_origins=ORIGINS, allow_methods=["*"], allow_headers=["*"])

if os.getenv("USE_MCP") == "1":                    # route the agent's tools through the MCP server
    from agent import mcp_client
    mcp_client.register_from_stdio(sys.executable, ["-m", "mcp_servers.support_tools"])

graph = build()
RUNS: list[dict] = []          # run log: metrics, audit and drift all read from here
DECISIONS: list[dict] = []     # human approvals/rejections; rejections with reasons are the override set
HANDOFFS: list[dict] = []
REPLIES: list[dict] = []

PARALLEL = ["photo", "invoice", "order", "classify"]
SERIAL = ["fuse", "act", "verify"]


def _sse(obj) -> str:
    return f"data: {json.dumps(obj)}\n\n"


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/claims/stream")
async def stream(claim: dict):
    async def gen():
        m = RunMetrics()
        cid = str(claim.get("id", "anon"))
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
        out = await asyncio.to_thread(graph.invoke, {"claim": claim})
        ms = round((time.perf_counter() - t0) * 1000, 2)
        history.record(claim.get("customer_id"))
        trace = tools.EVENTS.get(cid, [])
        ev = out.get("evidence") or {}
        amount = (out.get("invoice") or {}).get("amount_inr")
        draft = reply.draft(out["decision"], amount, cid)
        RUNS.append({"id": cid, "ts": time.time(), "decision": out["decision"]["decision"], "rule": out["decision"]["rule"],
                     "lane": out["decision"]["lane"], "ms": ms, "verified": out["verified"],
                     "recovered": any(not e["ok"] for e in trace), "claim_type": ev.get("claim_type"),
                     "cluster": (out.get("kind") or {}).get("cluster"), "est_refund_inr": ev.get("est_refund_inr"),
                     "amount_inr": amount, "trace": trace, "text": claim.get("text", "")})
        yield _sse({"final": out["decision"], "verified": out["verified"], "ms": ms, "trace": trace,
                    "evidence": ev, "draft_reply": draft})
    return StreamingResponse(gen(), media_type="text/event-stream")


@app.post("/photo/check")
def photo_check(body: dict):
    img = Image.open(io.BytesIO(base64.b64decode(body["image_b64"])))
    return quality_check(img)


@app.post("/voice/transcribe")
def transcribe(body: dict):
    return voice.transcribe(body["audio_b64"])


@app.post("/decisions")
def decide(body: dict):
    """Human approve/reject. Rejections require a reason; they feed the eval/override set."""
    if body.get("action") not in ("approve", "reject"):
        raise HTTPException(400, "action must be approve or reject")
    if body["action"] == "reject" and not str(body.get("reason", "")).strip():
        raise HTTPException(400, "reject needs a reason")
    rec = {"id": body["id"], "action": body["action"], "reason": body.get("reason", ""), "ts": time.time()}
    DECISIONS.append(rec)
    return rec


@app.post("/decisions/batch")
def decide_batch(body: dict):
    ids = body.get("ids", [])
    recs = [{"id": i, "action": "approve", "reason": "", "ts": time.time(), "batch": True} for i in ids]
    DECISIONS.extend(recs)
    return {"approved": len(recs)}


@app.get("/overrides")
def overrides():
    return [d for d in DECISIONS if d["action"] == "reject"]


@app.post("/handoff")
def handoff(body: dict):
    """Customer asks for a person. The full case (text, decision so far, trace) goes with it."""
    run = next((r for r in reversed(RUNS) if r["id"] == body.get("id")), None)
    rec = {"id": body.get("id"), "note": body.get("note", ""), "ts": time.time(), "case": run}
    HANDOFFS.append(rec)
    return {"queued": True, "position": len(HANDOFFS), "has_case": run is not None}


@app.get("/handoffs")
def handoffs():
    return HANDOFFS


@app.post("/replies")
def send_reply(body: dict):
    """Logs the reply the agent approved. Delivery (email / WhatsApp / SMS) is not wired up yet."""
    rec = {"id": body["id"], "text": body["text"], "ts": time.time(), "delivered": False}
    REPLIES.append(rec)
    return rec


_AUDIT_COLS = ["id", "ts", "decision", "rule", "lane", "ms", "verified", "recovered", "claim_type", "cluster",
               "amount_inr", "est_refund_inr", "trace"]


def _csv(runs) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=_AUDIT_COLS, extrasaction="ignore")
    w.writeheader()
    for r in runs:
        w.writerow({**r, "trace": json.dumps(r["trace"])})
    return buf.getvalue()


@app.get("/audit.csv", response_class=PlainTextResponse)
def audit_all():
    return _csv(RUNS)


@app.get("/audit/{claim_id}.csv", response_class=PlainTextResponse)
def audit_one(claim_id: str):
    rows = [r for r in RUNS if r["id"] == claim_id]
    if not rows:
        raise HTTPException(404, "unknown claim")
    return _csv(rows)


@app.get("/metrics")
def metrics():
    n = len(RUNS)
    if not n:
        return {"n": 0}
    lat = sorted(r["ms"] for r in RUNS)
    by = {}
    for r in RUNS:
        by[r["decision"]] = by.get(r["decision"], 0) + 1
    return {"n": n, "auto_resolve_rate": round(sum(r["lane"] == "ready" for r in RUNS) / n, 3),
            "verified_rate": round(sum(r["verified"] for r in RUNS) / n, 3),
            "p95_ms": lat[int(0.95 * (n - 1))], "recovered": sum(r["recovered"] for r in RUNS), "decisions": by,
            "overrides": sum(d["action"] == "reject" for d in DECISIONS), "handoffs": len(HANDOFFS)}


@app.get("/drift")
def drift_status():
    return drift.check(RUNS)


@app.get("/clusters")
def clusters():
    """Escalated/rejected runs grouped by the text cluster, labelled by top terms."""
    terms = predict.cluster_terms()
    counts: dict[int, int] = {}
    for r in RUNS:
        if r["decision"] != "approve" and r.get("cluster") is not None:
            counts[r["cluster"]] = counts.get(r["cluster"], 0) + 1
    return [{"cluster": c, "terms": terms.get(c, []), "count": n} for c, n in sorted(counts.items(), key=lambda x: -x[1])]
