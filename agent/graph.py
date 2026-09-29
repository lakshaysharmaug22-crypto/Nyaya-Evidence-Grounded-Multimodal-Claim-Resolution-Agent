"""LangGraph workflow: parallel evidence gathering -> fusion -> policy -> action -> verify."""
from typing import TypedDict
from langgraph.graph import StateGraph, START, END

from . import history, tools
from .policy import Evidence, decide
from ml import predict
from ml.dedupe import DupIndex
from ml.infer import damage_confidence
from ml.invoice import extract as extract_invoice
from ml.quality_gate import check as quality_check
import base64, io
from PIL import Image

_dups = DupIndex()


class State(TypedDict, total=False):
    claim: dict
    photo: dict
    invoice: dict
    order: dict
    kind: dict
    evidence: dict
    decision: dict
    action: dict
    verified: bool


def analyse_photo(s: State):
    c = s["claim"]
    b64 = c.get("image_b64")
    if not b64:                                   # no image: use supplied score (tests / mock claims)
        return {"photo": {"damage_conf": c.get("damage_conf", 0.0), "duplicate": False}}
    img = Image.open(io.BytesIO(base64.b64decode(b64)))
    q = quality_check(img)
    if not q["ok"]:
        return {"photo": {"damage_conf": 0.0, "duplicate": False, "quality": q}}
    d = _dups.check_and_add(c["id"], img)
    return {"photo": {"damage_conf": damage_confidence(img), "duplicate": d["duplicate"], "quality": q}}


def parse_invoice(s: State):
    c = s["claim"]
    if not c.get("invoice_b64"):
        return {"invoice": {"amount_inr": c.get("amount_inr", 0.0), "extracted": None}}
    ex = extract_invoice(c["invoice_b64"])
    amount = ex["amount_inr"] if ex["amount_inr"] is not None else c.get("amount_inr", 0.0)
    return {"invoice": {"amount_inr": amount, "extracted": ex}}


def lookup_order(s: State):
    r = tools.call("order_lookup", s["claim"]["id"], order_id=s["claim"]["order_id"])
    return {"order": r}


def classify(s: State):
    c = s["claim"]
    k = predict.classify(c.get("text", ""))
    k["cluster"] = predict.cluster(c.get("text", ""))
    return {"kind": k}


def fuse(s: State):
    c = s["claim"]
    kind = s.get("kind", {}).get("type")
    # cross-modal check: text says damage but the photo shows none
    text_photo_ok = not (kind == "damaged" and s["photo"]["damage_conf"] < 0.3)
    ex = s["invoice"].get("extracted")
    invoice_ok = True
    if ex is not None:                       # invoice must be readable and match the claim
        claimed = c.get("amount_inr")
        invoice_ok = (ex["order_id"] == c["order_id"] and ex["amount_inr"] is not None
                      and (claimed is None or abs(ex["amount_inr"] - claimed) <= 1))
    ev = Evidence(
        damage_conf=s["photo"]["damage_conf"],
        order_verified=s["order"]["found"],
        days_since_delivery=c.get("days_since_delivery", 0),
        amount_inr=s["invoice"]["amount_inr"],
        text_photo_invoice_agree=c.get("modalities_agree", True) and text_photo_ok and invoice_ok,
        duplicate_image=c.get("duplicate_image", False) or s["photo"].get("duplicate", False),
        repeat_claimant=c.get("repeat_claimant", False) or history.is_repeat(c.get("customer_id")),
    )
    est = predict.refund(kind, ev.amount_inr, ev.days_since_delivery, ev.damage_conf) if kind else None
    return {"evidence": {**ev.__dict__, "claim_type": kind, "est_refund_inr": est}, "decision": decide(ev)}


def act(s: State):
    if s["decision"]["decision"] != "approve":
        return {"action": {"status": "held_for_human"}}
    c = s["claim"]
    r = tools.call("issue_refund", c["id"], order_id=c["order_id"],
                   amount_inr=s["invoice"]["amount_inr"])
    tools.call("notify_customer", c["id"], order_id=c["order_id"], message="Refund issued")
    return {"action": r}


def verify(s: State):
    d = s["decision"]["decision"]
    ok = (d == "approve" and s["action"].get("status") == "issued") or \
         (d != "approve" and s["action"].get("status") == "held_for_human")
    return {"verified": ok}


def build():
    g = StateGraph(State)
    par = [("n_photo", analyse_photo), ("n_invoice", parse_invoice), ("n_order", lookup_order), ("n_classify", classify)]
    for name, fn in par + [("n_fuse", fuse), ("n_act", act), ("n_verify", verify)]:
        g.add_node(name, fn)
    for name, _ in par:                      # parallel evidence gathering
        g.add_edge(START, name)
    g.add_edge([n for n, _ in par], "n_fuse")  # fan-in: waits for all branches
    g.add_edge("n_fuse", "n_act")
    g.add_edge("n_act", "n_verify")
    g.add_edge("n_verify", END)
    return g.compile()
