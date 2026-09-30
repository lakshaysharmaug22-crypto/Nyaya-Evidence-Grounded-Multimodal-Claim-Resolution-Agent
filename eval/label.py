"""Build the human-verified gold set.

    python -m eval.label add --id G001 --order ORD4471 --text "Mug arrived cracked" \
        --photo ~/claims/mug.jpg --invoice ~/claims/mug.pdf --amount 499 --days 2 \
        --source hand_authored_real_evidence --customer c-17
    python -m eval.label annotate --annotator lakshay      # blind: never shows what Nyaya decided
    python -m eval.label agreement                          # Cohen's kappa + disagreements
    python -m eval.label adjudicate --id G001 --label reject --note "invoice total differs"
    python -m eval.label freeze                             # writes verified.jsonl with dev/test split
    python -m eval.label status

Files (eval/gold/verified/): cases.jsonl, annotations.jsonl (append-only), adjudications.jsonl,
media/ (EXIF-stripped copies), verified.jsonl (frozen output read by `python -m eval.run --set verified`).
The protocol is in eval/gold/README.md.
"""
import argparse
import hashlib
import json
import shutil
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).parent / "gold" / "verified"
CASES, ANN, ADJ, MEDIA, FROZEN = (ROOT / "cases.jsonl", ROOT / "annotations.jsonl", ROOT / "adjudications.jsonl",
                                  ROOT / "media", ROOT / "verified.jsonl")
LABELS = ("approve", "reject", "escalate")
SOURCES = ("real_customer", "hand_authored_real_evidence")
TEST_SHARE = 0.6                  # the larger share is the frozen test split


def _read(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()] if p.exists() else []


def _append(p: Path, rec: dict):
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _copy_media(src: str, case_id: str, kind: str) -> str:
    """Copy into the repo. Photos are re-encoded without EXIF so no GPS/device data is kept."""
    s = Path(src).expanduser()
    if not s.exists():
        sys.exit(f"missing file: {s}")
    MEDIA.mkdir(parents=True, exist_ok=True)
    if s.suffix.lower() == ".pdf":
        dst = MEDIA / f"{case_id}-{kind}.pdf"
        shutil.copyfile(s, dst)
    else:
        from PIL import Image
        dst = MEDIA / f"{case_id}-{kind}.jpg"
        im = Image.open(s).convert("RGB")
        clean = Image.new("RGB", im.size); clean.putdata(list(im.getdata()))
        clean.save(dst, quality=90)
    return str(dst.relative_to(ROOT))


def cmd_add(a):
    if any(c["id"] == a.id for c in _read(CASES)):
        sys.exit(f"{a.id} already exists")
    if a.source not in SOURCES:
        sys.exit(f"--source must be one of {SOURCES}; synthetic cases do not belong in the gold set")
    case = {"id": a.id, "order_id": a.order, "customer_id": a.customer, "text": a.text, "amount_inr": a.amount,
            "days_since_delivery": a.days, "source": a.source, "provenance": a.provenance, "added_ts": time.time()}
    if a.photo:
        case["photo"] = _copy_media(a.photo, a.id, "photo")
    if a.invoice:
        case["invoice"] = _copy_media(a.invoice, a.id, "invoice")
    _append(CASES, case)
    print("added", a.id)


def _show(c: dict):
    print(f"\n=== {c['id']}  ({c['source']})")
    print(f"order {c['order_id']}  customer {c.get('customer_id')}  amount ₹{c.get('amount_inr')}  "
          f"days since delivery {c.get('days_since_delivery')}")
    print(f"claim text: {c['text']}")
    for k in ("photo", "invoice"):
        if c.get(k):
            print(f"{k}: {ROOT / c[k]}   (open it before labelling)")


def cmd_annotate(a):
    done = {(x["id"], x["annotator"]) for x in _read(ANN)}
    todo = [c for c in _read(CASES) if (c["id"], a.annotator) not in done]
    print(f"{len(todo)} cases to label. Decide from the evidence and eval/gold/README.md only. q to stop.")
    for c in todo:
        _show(c)
        lab = input(f"label {LABELS}: ").strip().lower()
        if lab == "q":
            break
        if lab not in LABELS:
            print("skipped (not a valid label)"); continue
        why = input("one-line reason (cite the evidence): ").strip()
        conf = input("confidence 1-3: ").strip()
        _append(ANN, {"id": c["id"], "annotator": a.annotator, "label": lab, "reason": why,
                      "confidence": int(conf) if conf in {"1", "2", "3"} else None, "ts": time.time()})


def kappa(pairs: list[tuple[str, str]]) -> float | None:
    if not pairs:
        return None
    n = len(pairs)
    po = sum(x == y for x, y in pairs) / n
    ca, cb = Counter(x for x, _ in pairs), Counter(y for _, y in pairs)
    pe = sum(ca[l] * cb[l] for l in LABELS) / (n * n)
    return round((po - pe) / (1 - pe), 4) if pe < 1 else 1.0


def _by_case():
    d = defaultdict(dict)
    for x in _read(ANN):
        d[x["id"]][x["annotator"]] = x
    return d


def agreement() -> dict:
    by = _by_case()
    pairs, disagree = [], []
    for cid, anns in by.items():
        if len(anns) >= 2:
            a, b = sorted(anns)[:2]
            pairs.append((anns[a]["label"], anns[b]["label"]))
            if anns[a]["label"] != anns[b]["label"]:
                disagree.append({"id": cid, a: anns[a]["label"], b: anns[b]["label"]})
    return {"double_annotated": len(pairs), "raw_agreement": round(sum(x == y for x, y in pairs) / len(pairs), 4) if pairs else None,
            "cohens_kappa": kappa(pairs), "disagreements": disagree}


def cmd_agreement(a):
    print(json.dumps(agreement(), indent=2))


def cmd_adjudicate(a):
    if a.label not in LABELS:
        sys.exit(f"--label must be one of {LABELS}")
    _append(ADJ, {"id": a.id, "label": a.label, "note": a.note, "by": a.by, "ts": time.time()})


def _split(case: dict) -> str:
    """Deterministic, grouped by customer (or order) so one customer never spans dev and test."""
    key = case.get("customer_id") or case["order_id"]
    return "test" if int(hashlib.sha256(key.encode()).hexdigest(), 16) % 100 < TEST_SHARE * 100 else "dev"


def cmd_freeze(a):
    by, adj = _by_case(), {x["id"]: x for x in _read(ADJ)}
    out, skipped = [], []
    for c in _read(CASES):
        anns = by.get(c["id"], {})
        labels = {x["label"] for x in anns.values()}
        if len(anns) < 2:
            skipped.append((c["id"], "needs two annotators")); continue
        if len(labels) == 1:
            gold, how = labels.pop(), "agreed"
        elif c["id"] in adj:
            gold, how = adj[c["id"]]["label"], "adjudicated"
        else:
            skipped.append((c["id"], "disagreement not adjudicated")); continue
        out.append({**c, "expected": gold, "label_method": how, "annotators": sorted(anns), "split": _split(c)})
    FROZEN.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in out))
    digest = hashlib.sha256(FROZEN.read_bytes()).hexdigest()[:16]
    print(json.dumps({"frozen": len(out), "skipped": skipped, "splits": Counter(r["split"] for r in out),
                      "labels": Counter(r["expected"] for r in out), "sha256": digest,
                      "agreement": {k: v for k, v in agreement().items() if k != "disagreements"}}, indent=2, default=dict))


def cmd_status(a):
    cases, anns = _read(CASES), _read(ANN)
    print(json.dumps({"cases": len(cases), "sources": Counter(c["source"] for c in cases),
                      "annotations": Counter(x["annotator"] for x in anns), "frozen": len(_read(FROZEN))}, indent=2, default=dict))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m eval.label")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("add")
    p.add_argument("--id", required=True); p.add_argument("--order", required=True); p.add_argument("--text", required=True)
    p.add_argument("--customer"); p.add_argument("--photo"); p.add_argument("--invoice")
    p.add_argument("--amount", type=float); p.add_argument("--days", type=int, default=0)
    p.add_argument("--source", required=True, choices=SOURCES)
    p.add_argument("--provenance", default="", help="where the evidence came from, e.g. 'own order, photo taken 2026-10-02'")
    p.set_defaults(fn=cmd_add)
    p = sub.add_parser("annotate"); p.add_argument("--annotator", required=True); p.set_defaults(fn=cmd_annotate)
    sub.add_parser("agreement").set_defaults(fn=cmd_agreement)
    p = sub.add_parser("adjudicate")
    p.add_argument("--id", required=True); p.add_argument("--label", required=True); p.add_argument("--note", required=True)
    p.add_argument("--by", default="adjudicator"); p.set_defaults(fn=cmd_adjudicate)
    sub.add_parser("freeze").set_defaults(fn=cmd_freeze)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
