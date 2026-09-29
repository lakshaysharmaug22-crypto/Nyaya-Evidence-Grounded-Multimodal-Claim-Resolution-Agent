"""FastAPI app with SSE streaming of the claim run (node-by-node)."""
import asyncio
import json

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

import base64, io, time
from PIL import Image

from agent import tools
from agent.graph import build
from ml.quality_gate import check as quality_check
from agent.metrics import RunMetrics

app = FastAPI(title="Support Resolution Agent")
import os
ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",")]
app.add_middleware(CORSMiddleware, allow_origins=ORIGINS, allow_methods=["*"], allow_headers=["*"])
graph = build()
RUNS: list[dict] = []          # in-memory run log for the manager view

PARALLEL = ["photo", "invoice", "order", "classify"]
SERIAL = ["fuse", "act", "verify"]


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/claims/stream")
async def stream(claim: dict):
    async def gen():
        m = RunMetrics()
        state = {"claim": claim}
        for n in PARALLEL:
            yield f"data: {json.dumps({'node': n, 'status': 'running'})}\n\n"
        await asyncio.sleep(0.4)
        for n in PARALLEL:
            with m.node(n):
                pass
            yield f"data: {json.dumps({'node': n, 'status': 'done'})}\n\n"
        for n in SERIAL:
            yield f"data: {json.dumps({'node': n, 'status': 'running'})}\n\n"
            await asyncio.sleep(0.3)
            with m.node(n):
                pass
            yield f"data: {json.dumps({'node': n, 'status': 'done'})}\n\n"
        cid = str(claim.get("id", "anon"))
        if claim.get("inject_failure"):            # demo: order lookup fails once, retry recovers
            tools.FAIL_ONCE.add(f"order_lookup:{cid}")
        t0 = time.perf_counter()
        out = graph.invoke(state)
        ms = round((time.perf_counter() - t0) * 1000, 2)
        trace = tools.EVENTS.get(cid, [])
        RUNS.append({"id": cid, "decision": out["decision"]["decision"], "rule": out["decision"]["rule"],
                     "lane": out["decision"]["lane"], "ms": ms, "verified": out["verified"], "ts": time.time(),
                     "recovered": any(not e["ok"] for e in trace)})
        yield f"data: {json.dumps({'final': out['decision'], 'verified': out['verified'], 'ms': ms, 'trace': trace, 'evidence': out.get('evidence')})}\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream")


@app.post("/photo/check")
def photo_check(body: dict):
    img = Image.open(io.BytesIO(base64.b64decode(body["image_b64"])))
    return quality_check(img)


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
            "p95_ms": lat[int(0.95 * (n - 1))], "recovered": sum(r["recovered"] for r in RUNS), "decisions": by}
