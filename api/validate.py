"""Request validation for the public and agent endpoints. Errors become 422 with a plain message."""
import base64
import binascii
import re

from fastapi import HTTPException

ID = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")
SCORE_FIELDS = ("damage_conf", "modalities_agree", "duplicate_image", "repeat_claimant", "inject_failure")
MAX_TEXT = 4000
MAX_UPLOAD_MB = 8


def _bad(msg: str):
    raise HTTPException(422, msg)


def ident(v, name: str, required: bool = True) -> str | None:
    if v is None or v == "":
        if required:
            _bad(f"{name} is required")
        return None
    v = str(v).strip()
    if not ID.match(v):
        _bad(f"{name} must be 1-64 characters: letters, digits, . _ : -")
    return v


def text(v, name: str = "text", limit: int = MAX_TEXT, required: bool = False) -> str:
    if v is None:
        if required:
            _bad(f"{name} is required")
        return ""
    if not isinstance(v, str):
        _bad(f"{name} must be a string")
    v = "".join(ch for ch in v if ch.isprintable() or ch in "\n\t")
    if required and not v.strip():
        _bad(f"{name} is required")
    if len(v) > limit:
        _bad(f"{name} is longer than {limit} characters")
    return v


def b64(v, name: str, limit_mb: int = MAX_UPLOAD_MB) -> str:
    if not isinstance(v, str):
        _bad(f"{name} must be base64 text")
    if len(v) > limit_mb * 1024 * 1024 * 4 // 3 + 4:
        _bad(f"{name} is larger than {limit_mb} MB")
    try:
        base64.b64decode(v, validate=True)
    except (binascii.Error, ValueError):
        _bad(f"{name} is not valid base64")
    return v


def number(v, name: str, lo: float, hi: float):
    if v is None:
        return None
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        _bad(f"{name} must be a number")
    if not lo <= v <= hi:
        _bad(f"{name} must be between {lo} and {hi}")
    return v


def claim(body, trusted: bool) -> dict:
    """Validate a claim. Untrusted callers cannot supply model scores or demo switches."""
    if not isinstance(body, dict):
        _bad("claim must be a JSON object")
    c = dict(body)
    c["id"] = ident(c.get("id") or "anon", "id")
    c["order_id"] = ident(c.get("order_id"), "order_id", required=False) or ""
    c["customer_id"] = ident(c.get("customer_id"), "customer_id", required=False)
    c["text"] = text(c.get("text"))
    number(c.get("amount_inr"), "amount_inr", 0, 10_000_000)
    number(c.get("days_since_delivery"), "days_since_delivery", 0, 3650)
    number(c.get("damage_conf"), "damage_conf", 0, 1)
    for key in ("image_b64", "invoice_b64"):
        if c.get(key):
            b64(c[key], key)
    if not trusted:
        for f in SCORE_FIELDS:
            c.pop(f, None)
    return c
