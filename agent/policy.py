"""Deterministic policy engine. The LLM reads evidence; rules decide."""
from dataclasses import dataclass

RETURN_WINDOW_DAYS = 7
AUTO_APPROVE_MAX_INR = 5000
AUTO_APPROVE_MIN_CONF = 0.90
OUTLIER_RATIO = 2.5          # claimed amount vs the regression's expected refund


@dataclass
class Evidence:
    damage_conf: float
    order_verified: bool
    days_since_delivery: int
    amount_inr: float
    text_photo_invoice_agree: bool
    duplicate_image: bool
    repeat_claimant: bool
    suspicious_text: bool = False      # instruction-like text in the customer's message
    amount_ratio: float | None = None  # claimed amount / expected refund, when the regressor has an estimate


def decide(e: Evidence) -> dict:
    if e.duplicate_image:
        return {"decision": "escalate", "rule": "duplicate_image", "lane": "review"}
    if not e.order_verified:
        return {"decision": "reject", "rule": "order_not_found", "lane": "review"}
    if e.days_since_delivery > RETURN_WINDOW_DAYS:
        return {"decision": "reject", "rule": "outside_window", "lane": "review"}
    if e.suspicious_text:
        return {"decision": "escalate", "rule": "suspicious_text", "lane": "review"}
    if not e.text_photo_invoice_agree:
        return {"decision": "escalate", "rule": "cross_modal_mismatch", "lane": "review"}
    if e.amount_ratio is not None and e.amount_ratio > OUTLIER_RATIO:
        return {"decision": "escalate", "rule": "amount_outlier", "lane": "review"}
    if (e.damage_conf >= AUTO_APPROVE_MIN_CONF and e.amount_inr <= AUTO_APPROVE_MAX_INR
            and not e.repeat_claimant):
        return {"decision": "approve", "rule": "auto_approve", "lane": "ready"}
    return {"decision": "escalate", "rule": "low_confidence_or_high_value", "lane": "review"}
