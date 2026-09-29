"""Ablation: fused pipeline vs single-modality baselines on the gold set.
Run: python -m eval.ablation   (writes eval/ablation.json)
"""
import json
from pathlib import Path

from agent.graph import build

ROOT = Path(__file__).parent


def main():
    cases = json.loads((ROOT / "gold" / "cases.json").read_text())
    g = build()
    photo_only = text_only = fused = 0
    for c in cases:
        cl, exp = c["claim"], c["expected"]
        photo_only += ("approve" if cl.get("damage_conf", 0) >= .9 else "escalate") == exp
        text_only += ("approve" if "broken" in cl.get("text", "") or "crushed" in cl.get("text", "") else "escalate") == exp
        fused += g.invoke({"claim": cl})["decision"]["decision"] == exp
    n = len(cases)
    r = {"n": n, "photo_only": round(photo_only / n, 3), "text_only": round(text_only / n, 3), "fused": round(fused / n, 3),
         "note": "gold set is synthetic; rerun on hand-verified real claims before quoting"}
    (ROOT / "ablation.json").write_text(json.dumps(r, indent=2))
    print(json.dumps(r, indent=2))


if __name__ == "__main__":
    main()
