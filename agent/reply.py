"""Deterministic customer reply drafts. No LLM: predictable, auditable, free."""

RULE_TEXT = {
    "auto_approve": "We checked your photo, invoice and order details and approved a refund of {amt}. It will reach your original payment method in 5-7 working days.",
    "outside_window": "Your claim arrived after our 7-day window from delivery, so we are unable to approve it automatically. If you think this is wrong, reply here and a team member will review it.",
    "order_not_found": "We could not find an order matching the details you sent. Please reply with your order ID or invoice and we will look again.",
    "duplicate_image": "The photo in this claim matches one we already have on file, so a team member will review it before we proceed. You do not need to do anything right now.",
    "cross_modal_mismatch": "Some details in your message, photo and invoice did not line up, so a team member is checking your case. We will update you shortly.",
    "low_confidence_or_high_value": "A team member is reviewing your claim to make sure it is handled correctly. We will update you as soon as that is done.",
}


def draft(decision: dict, amount_inr: float | None, claim_id: str) -> str:
    rule = decision.get("rule", "low_confidence_or_high_value")
    body = RULE_TEXT.get(rule, RULE_TEXT["low_confidence_or_high_value"])
    amt = f"₹{amount_inr:,.0f}" if amount_inr else "the claimed amount"
    return f"Hi, regarding claim {claim_id}: " + body.format(amt=amt)
