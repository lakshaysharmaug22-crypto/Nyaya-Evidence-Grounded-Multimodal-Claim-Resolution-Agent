# Support Resolution Agent

Multimodal claim-resolution system: parallel evidence gathering, cross-modal fusion, a deterministic policy engine, idempotent tools, and an eval harness gated in CI.

## Run

```
sh scripts/bootstrap.sh
uvicorn api.main:app --reload        # API on :8000
cd web && npm run dev                # UI on :3000
python -m eval.run --gate            # eval vs baseline
```

The UI runs on a local mock stream when `NEXT_PUBLIC_API_URL` is unset, so `web/` deploys to Vercel as-is.

## Layout

- `agent/` policy engine, tool registry, LangGraph workflow, metrics
- `api/` FastAPI with SSE streaming
- `eval/` gold cases, baseline, harness
- `ml/` CNN, classifier, regression, clustering (next)
- `web/` Next.js UI

## MCP tools

The three tools (order lookup, refund, customer notification) are served by an MCP server: `python -m mcp_servers.support_tools`. The agent can load them from any MCP server over stdio (`agent/mcp_client.py`); set `USE_MCP=1` on the API to route its tool calls through the server. Retries and idempotency keys apply the same way over MCP.

## Features

- Photo quality gate, duplicate-image check, invoice PDF/image extraction (Tesseract)
- Console: draft reply (editable), batch approve for the ready lane, A/R hotkeys, rejection reasons saved as an override set, per-case audit CSV
- Customer: human handoff carrying the full case, optional voice notes (`requirements-optional.txt`)
- Insights: drift alerts, failure clusters with readable labels, policy simulator
- Repeat-claimant check from claim history (3 prior claims in 30 days blocks auto-approve)

Reply delivery (email / WhatsApp) is logged only and not connected yet.

## Deploy

1. **API on Render:** New > Blueprint, point at this repo (`render.yaml`). Set `ALLOWED_ORIGINS` to your Vercel URL. The free tier sleeps when idle, so the first request is slow.
2. **Web on Vercel:** import the repo, set the root directory to `web`, and set `NEXT_PUBLIC_API_URL` to the Render URL. Without that variable the UI runs on its built-in mock stream.
3. Train the CNN on Colab (`ml/README.md`), commit nothing large, and put `damage.int8.onnx` in `ml/artifacts/`. Add a `COPY` for it or mount it before enabling real image scoring in production.

## Tests

`pip install -r requirements-dev.txt && python -m ml.train_tabular && python -m pytest -q` (needs `tesseract-ocr` installed).

## Demo mode

Open `/console?demo=1` for the interviewer tools: inject a tool failure (order lookup fails once, the retry recovers) and scrub through the recorded run. `/insights` has the metrics tiles and a policy simulator that replays sample cases against changed thresholds.

## Status

Working: parallel agent graph, policy engine, retries, photo quality gate, duplicate check, tabular models, eval gate, glass UI. Pending: CNN weights, invoice OCR, voice, real gold set.
