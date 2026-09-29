from PIL import Image
from ml.quality_gate import check
from ml.dedupe import DupIndex
from ml.invoice import extract, parse_text
import base64


def test_quality_gate_sharp_blur_dark(png_b64):
    import io
    load = lambda **k: Image.open(io.BytesIO(base64.b64decode(png_b64(**k))))
    assert check(load())["ok"]
    assert check(load(blur=8))["reason"] == "blurry"
    assert check(Image.new("RGB", (480, 480), (10, 10, 10)))["reason"] == "too_dark"
    assert check(Image.new("RGB", (100, 100), (128, 128, 128)))["reason"] == "too_small"

def test_dedupe_flags_resized_copy_not_different(png_b64):
    import io
    load = lambda s: Image.open(io.BytesIO(base64.b64decode(png_b64(seed=s))))
    idx = DupIndex()
    a = load(1)
    assert not idx.check_and_add("A", a)["duplicate"]
    assert idx.check_and_add("B", a.resize((300, 300)))["duplicate"]
    assert not idx.check_and_add("C", load(7))["duplicate"]

def test_invoice_pdf_extraction(invoice_pdf_b64):
    r = extract(invoice_pdf_b64("ORD-4821", "2,499.00"))
    assert (r["order_id"], r["amount_inr"], r["source"]) == ("ORD4821", 2499.0, "pdf_text")

def test_invoice_garbage_is_safe():
    assert extract(base64.b64encode(b"junk").decode())["amount_inr"] is None

def test_parse_text_takes_grand_total():
    assert parse_text("Item Rs 100\nTotal: Rs 100\nGrand Total Rs 1,180.50")["amount_inr"] == 1180.5
