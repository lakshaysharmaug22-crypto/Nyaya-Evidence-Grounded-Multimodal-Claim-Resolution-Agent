import base64, io
import pytest
from PIL import Image
import numpy as np


def _png(seed=1, blur=0):
    from PIL import ImageFilter
    rng = np.random.default_rng(seed)
    im = Image.fromarray(np.kron(rng.integers(0, 255, (12, 12, 3)), np.ones((40, 40, 1))).astype("uint8"))
    if blur:
        im = im.filter(ImageFilter.GaussianBlur(blur))
    b = io.BytesIO(); im.save(b, "PNG")
    return b.getvalue()


@pytest.fixture
def png_b64():
    return lambda seed=1, blur=0: base64.b64encode(_png(seed, blur)).decode()


@pytest.fixture
def invoice_pdf_b64():
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    def make(order="ORD-1001", total="1,499.00"):
        b = io.BytesIO(); c = canvas.Canvas(b, pagesize=A4)
        for i, t in enumerate(["Tax Invoice", f"Order No: {order}", "Date: 12/09/2026", f"Total Amount: Rs. {total}"]):
            c.drawString(72, 780 - i * 24, t)
        c.save()
        return base64.b64encode(b.getvalue()).decode()
    return make
