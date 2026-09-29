"""Synthetic claim generator. Metrics on this data are optimistic: replace with real or hand-verified claims before quoting numbers."""
import random

TYPES = ["damaged", "wrong_item", "missing_item", "late_delivery", "billing"]
TEMPLATES = {
    "damaged": ["screen is cracked when it arrived", "box was crushed and the item is broken", "product came with a dent and scratches",
                "the bottle leaked and packaging was torn", "received it damaged, photo attached"],
    "wrong_item": ["i ordered a blue one but got a red one", "wrong product delivered, different model", "received someone else's order",
                   "size is different from what i ordered", "item does not match the listing"],
    "missing_item": ["one item missing from my package", "box was empty", "charger not included in the box",
                     "only two of three items arrived", "part of the order never came"],
    "late_delivery": ["order arrived two weeks late", "delivery delayed again and again", "still waiting past the promised date",
                      "package came far too late for the event", "tracking stuck for days"],
    "billing": ["charged twice for the same order", "refund not received yet", "wrong amount debited",
                "coupon not applied at billing", "invoice total does not match payment"],
}
FILLER = ["please help", "this is urgent", "very disappointed", "need a refund", "thanks", "order id below", "kindly check"]
SEVERITY = {"damaged": (0.4, 1.0), "wrong_item": (0.7, 1.0), "missing_item": (0.5, 1.0), "late_delivery": (0.1, 0.4), "billing": (0.5, 1.0)}


def make(n: int, seed: int = 11) -> list[dict]:
    r = random.Random(seed)
    rows = []
    for i in range(n):
        t = r.choice(TYPES)
        text = r.choice(TEMPLATES[t]) + (" " + r.choice(FILLER) if r.random() < .6 else "")
        price = r.choice([299, 499, 999, 1499, 2499, 3999, 5999])
        lo, hi = SEVERITY[t]
        sev = round(r.uniform(lo, hi), 2)
        days = r.randint(0, 12)
        conf = min(1.0, max(0.0, sev + r.gauss(0, .08))) if t == "damaged" else r.uniform(.2, .6)
        refund = round(price * sev * (1 if t != "late_delivery" else .3) + r.gauss(0, price * .03), 2)
        rows.append({"id": f"S{i:05d}", "text": text, "type": t, "price": price, "severity": sev,
                     "days": days, "damage_conf": round(conf, 3), "refund": max(0.0, refund)})
    return rows
