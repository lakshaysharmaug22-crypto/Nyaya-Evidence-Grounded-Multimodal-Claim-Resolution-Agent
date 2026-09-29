"""Eval harness. `python -m eval.run` prints metrics; `--gate` fails on regression vs baseline."""
import json
import sys
import time
from pathlib import Path

from agent import graph as G
from agent import llm
from agent.graph import build

ROOT = Path(__file__).parent
GOLD = ROOT / "gold" / "cases.json"
BASELINE = ROOT / "baseline.json"


def run() -> dict:
    if "--llm" in sys.argv:                       # real model, when ANTHROPIC_API_KEY is set
        model = llm.get_llm()
        if model is None:
            sys.exit("--llm needs ANTHROPIC_API_KEY (and langchain-anthropic)")
        G.set_reader(llm.Reader(model))
    graph = build()
    cases = json.loads(GOLD.read_text())
    correct, verified, lat, briefs = 0, 0, [], []
    for c in cases:
        t = time.perf_counter()
        out = graph.invoke({"claim": c["claim"]})
        lat.append((time.perf_counter() - t) * 1000)
        correct += out["decision"]["decision"] == c["expected"]
        verified += bool(out["verified"])
        if out.get("brief"):
            briefs.append(out["brief"])
    lat.sort()
    tab = ROOT.parent / "ml" / "artifacts" / "tabular_metrics.json"
    extra = json.loads(tab.read_text()) if tab.exists() else {}
    return {**extra, 
        "n": len(cases),
        "decision_accuracy": round(correct / len(cases), 4),
        "verification_rate": round(verified / len(cases), 4),
        "p95_ms": round(lat[int(0.95 * (len(lat) - 1))], 2),
        # share of cases the policy could not settle, i.e. the only ones that reach the LLM
        "llm_routed_rate": round(len(briefs) / len(cases), 4),
        "llm_used_rate": round(sum(b["llm_used"] for b in briefs) / len(cases), 4),
        "avg_cost_inr": round(sum(b["cost_inr"] for b in briefs) / len(cases), 4),
        "groundedness": (round(sum(g) / len(g), 4) if (g := [b["groundedness"] for b in briefs if b.get("groundedness") is not None]) else None),
    }


def gate(m: dict) -> int:
    if not BASELINE.exists():
        print("no baseline; skipping gate")
        return 0
    b = json.loads(BASELINE.read_text())
    fails = []
    if m["decision_accuracy"] < b["decision_accuracy"]:
        fails.append("decision_accuracy regressed")
    if m["verification_rate"] < b["verification_rate"]:
        fails.append("verification_rate regressed")
    if m["p95_ms"] > b["p95_ms"] * 1.25 + 5:
        fails.append("p95_ms regressed")
    for f in fails:
        print("FAIL:", f)
    return 1 if fails else 0


if __name__ == "__main__":
    m = run()
    print(json.dumps(m, indent=2))
    (ROOT / "last_run.json").write_text(json.dumps(m, indent=2))
    if "--gate" in sys.argv:
        sys.exit(gate(m))
