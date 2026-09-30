"""Human labels for cases whose final agent action differs from the policy result."""


def learning_queue(runs: list[dict], decisions: list[dict]) -> list[dict]:
    """Return reviewed disagreements as labeled examples; policy output is never changed."""
    by_id = {str(run.get("id")): run for run in runs}
    rows = []
    for decision in decisions:
        run = by_id.get(str(decision.get("id")))
        if not run or decision.get("action") not in ("approve", "reject"):
            continue
        if run.get("decision") == decision["action"]:
            continue
        rows.append({
            "id": run["id"],
            "text": run.get("text", ""),
            "model_decision": run.get("decision"),
            "model_rule": run.get("rule"),
            "label": decision["action"],
            "label_reason": decision.get("reason", ""),
            "ts": decision.get("ts"),
        })
    return rows
