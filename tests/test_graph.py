from agent.graph import build
from agent import tools

g = build()
CLEAR = {"id": "G1", "order_id": "ORD1001", "damage_conf": 0.95, "amount_inr": 1499, "days_since_delivery": 2,
         "text": "box was crushed and the item is broken"}


def run(**kw):
    c = {**CLEAR, **kw}
    return g.invoke({"claim": c})


def test_clear_case_refunds_and_verifies():
    out = run(id="G-a")
    assert out["decision"]["decision"] == "approve" and out["action"]["status"] == "issued" and out["verified"]

def test_text_photo_mismatch_escalates():
    out = run(id="G-b", damage_conf=0.1)
    assert out["decision"]["decision"] == "escalate" and out["action"]["status"] == "held_for_human"

def test_invoice_order_mismatch_escalates(invoice_pdf_b64):
    out = run(id="G-c", invoice_b64=invoice_pdf_b64("ORD-9999", "1,499.00"))
    assert out["decision"]["rule"] == "cross_modal_mismatch"

def test_invoice_amount_mismatch_escalates(invoice_pdf_b64):
    out = run(id="G-d", invoice_b64=invoice_pdf_b64("ORD-1001", "9,999.00"))
    assert out["decision"]["rule"] == "cross_modal_mismatch"

def test_matching_invoice_approves(invoice_pdf_b64):
    out = run(id="G-e", invoice_b64=invoice_pdf_b64("ORD-1001", "1,499.00"))
    assert out["decision"]["decision"] == "approve"

def test_failure_injection_recovers_without_double_refund():
    tools.FAIL_ONCE.add("order_lookup:G-f")
    out = run(id="G-f")
    assert out["decision"]["decision"] == "approve"
    assert [e["ok"] for e in tools.EVENTS["G-f"] if e["tool"] == "order_lookup"] == [False, True]
    assert len([e for e in tools.EVENTS["G-f"] if e["tool"] == "issue_refund"]) == 1

def test_duplicate_photo_escalates(png_b64):
    a = run(id="D-1", image_b64=png_b64(seed=3))
    b = run(id="D-2", image_b64=png_b64(seed=3))
    assert b["decision"]["rule"] in ("duplicate_image", "low_confidence_or_high_value")
    assert b["photo"]["duplicate"] is True
