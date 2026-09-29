from agent.policy import Evidence, decide

BASE = dict(damage_conf=0.95, order_verified=True, days_since_delivery=2, amount_inr=1499,
            text_photo_invoice_agree=True, duplicate_image=False, repeat_claimant=False)


def d(**kw):
    return decide(Evidence(**{**BASE, **kw}))


def test_clear_case_auto_approves():
    assert d()["decision"] == "approve" and d()["lane"] == "ready"

def test_duplicate_image_escalates_first():
    assert d(duplicate_image=True, order_verified=False)["rule"] == "duplicate_image"

def test_unknown_order_rejected():
    assert d(order_verified=False)["decision"] == "reject"

def test_outside_window_rejected():
    assert d(days_since_delivery=8)["rule"] == "outside_window"
    assert d(days_since_delivery=7)["decision"] == "approve"          # boundary is inclusive

def test_cross_modal_mismatch_escalates():
    assert d(text_photo_invoice_agree=False)["rule"] == "cross_modal_mismatch"

def test_thresholds_are_inclusive():
    assert d(damage_conf=0.90)["decision"] == "approve"
    assert d(damage_conf=0.899)["decision"] == "escalate"
    assert d(amount_inr=5000)["decision"] == "approve"
    assert d(amount_inr=5001)["decision"] == "escalate"

def test_repeat_claimant_never_auto_approves():
    assert d(repeat_claimant=True)["decision"] == "escalate"
