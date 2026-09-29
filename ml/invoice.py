"""Invoice field extraction: text PDFs via pypdf, images and scanned pages via Tesseract.
Returns order_id, total amount (INR) and date when found, plus a confidence-style `source` tag.
"""
import base64
import io
import re

from PIL import Image

ORDER_RE = re.compile(r"\b(ORD[-\s]?\d{3,})\b", re.I)
AMOUNT_RE = re.compile(r"(?:grand\s*total|total\s*amount|amount\s*paid|total)\D{0,20}?(?:₹|rs\.?|inr)?\s*([0-9][0-9,]*(?:\.\d{1,2})?)", re.I)
DATE_RE = re.compile(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2})\b")


def _pdf_text(data: bytes) -> str:
    from pypdf import PdfReader
    return "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(data)).pages)


def _image_text(img: Image.Image) -> str:
    import pytesseract
    g = img.convert("L")
    if g.width < 1000:                                   # small scans OCR poorly; upscale
        g = g.resize((g.width * 2, g.height * 2), Image.LANCZOS)
    return pytesseract.image_to_string(g)


def parse_text(text: str) -> dict:
    order = ORDER_RE.search(text)
    amounts = [float(m.replace(",", "")) for m in AMOUNT_RE.findall(text)]
    date = DATE_RE.search(text)
    return {"order_id": order.group(1).replace(" ", "").replace("-", "").upper() if order else None,
            "amount_inr": max(amounts) if amounts else None,        # the grand total is the largest labelled amount
            "date": date.group(1) if date else None}


def extract(b64: str) -> dict:
    data = base64.b64decode(b64)
    try:
        if data[:5] == b"%PDF-":
            text, source = _pdf_text(data), "pdf_text"
            if len(text.strip()) < 20:                    # scanned PDF: no text layer
                return {"order_id": None, "amount_inr": None, "date": None, "source": "scanned_pdf_unsupported"}
        else:
            text, source = _image_text(Image.open(io.BytesIO(data))), "ocr"
    except Exception as e:                                # corrupt file, missing tesseract, etc.
        return {"order_id": None, "amount_inr": None, "date": None, "source": f"error:{type(e).__name__}"}
    return {**parse_text(text), "source": source}
