"""Drift alerts: compare a recent window of runs against an earlier reference window."""


def _stats(runs):
    n = len(runs)
    lat = sorted(r["ms"] for r in runs)
    return {"n": n, "auto_resolve": sum(r["lane"] == "ready" for r in runs) / n,
            "escalation": sum(r["decision"] == "escalate" for r in runs) / n,
            "verified": sum(r["verified"] for r in runs) / n, "p95_ms": lat[int(0.95 * (n - 1))]}


def check(runs: list[dict], window: int = 20) -> dict:
    if len(runs) < window * 2:
        return {"status": "insufficient_data", "needed": window * 2, "have": len(runs), "alerts": []}
    ref, cur = _stats(runs[-2 * window:-window]), _stats(runs[-window:])
    alerts = []
    if cur["auto_resolve"] < ref["auto_resolve"] - 0.15:
        alerts.append({"metric": "auto_resolve", "ref": round(ref["auto_resolve"], 3), "now": round(cur["auto_resolve"], 3)})
    if cur["escalation"] > ref["escalation"] + 0.20:
        alerts.append({"metric": "escalation", "ref": round(ref["escalation"], 3), "now": round(cur["escalation"], 3)})
    if cur["verified"] < 0.95:
        alerts.append({"metric": "verified", "ref": round(ref["verified"], 3), "now": round(cur["verified"], 3)})
    if cur["p95_ms"] > ref["p95_ms"] * 1.5 + 5:
        alerts.append({"metric": "p95_ms", "ref": round(ref["p95_ms"], 1), "now": round(cur["p95_ms"], 1)})
    return {"status": "alert" if alerts else "ok", "alerts": alerts, "reference": ref, "current": cur}
