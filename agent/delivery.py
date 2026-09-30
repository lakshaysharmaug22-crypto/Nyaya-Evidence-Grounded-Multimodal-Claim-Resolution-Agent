"""Reply delivery. Nothing leaves the system unless all three hold:

1. an agent approved this exact text (`approved: true` on an authenticated request),
2. REPLY_MODE is not `dry_run` (the default), and
3. the destination is on REPLY_ALLOWLIST (exact addresses/numbers or `@domain.com`).

Channels
- `webhook`: HTTPS POST of {claim_id, to, text} to REPLY_WEBHOOK_URL (n8n, Zapier, a WhatsApp/SMS
  provider bridge). Optional REPLY_WEBHOOK_SECRET is sent as an HMAC-SHA256 signature header.
- `smtp`: plain email through SMTP_HOST / SMTP_PORT / SMTP_USER / SMTP_PASSWORD / SMTP_FROM (STARTTLS).

Every attempt is idempotent on the reply id: a retried request never sends twice.
"""
import hashlib
import hmac
import json
import os
import re
import smtplib
import urllib.request
from email.message import EmailMessage

MODES = {"dry_run", "webhook", "smtp"}
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE = re.compile(r"^\+?[0-9]{8,15}$")
_sent: dict[str, dict] = {}


class DeliveryError(Exception):
    pass


def mode() -> str:
    m = os.getenv("REPLY_MODE", "dry_run").strip().lower()
    return m if m in MODES else "dry_run"


def _allowlist() -> list[str]:
    return [a.strip().lower() for a in os.getenv("REPLY_ALLOWLIST", "").split(",") if a.strip()]


def allowed(to: str) -> bool:
    to = (to or "").strip().lower()
    if not (_EMAIL.match(to) or _PHONE.match(to)):
        return False
    for a in _allowlist():
        if to == a or (a.startswith("@") and to.endswith(a)):
            return True
    return False


def _webhook(claim_id: str, to: str, text: str):
    url = os.getenv("REPLY_WEBHOOK_URL", "")
    if not url.startswith("https://"):
        raise DeliveryError("REPLY_WEBHOOK_URL must be an https URL")
    body = json.dumps({"claim_id": claim_id, "to": to, "text": text}).encode()
    headers = {"Content-Type": "application/json"}
    secret = os.getenv("REPLY_WEBHOOK_SECRET")
    if secret:
        headers["X-Nyaya-Signature"] = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=10) as r:          # noqa: S310 (https enforced above)
        if r.status >= 300:
            raise DeliveryError(f"webhook answered {r.status}")


def _smtp(claim_id: str, to: str, text: str):
    host, sender = os.getenv("SMTP_HOST"), os.getenv("SMTP_FROM")
    if not host or not sender:
        raise DeliveryError("SMTP_HOST and SMTP_FROM are required")
    if not _EMAIL.match(to):
        raise DeliveryError("smtp channel needs an email address")
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = sender, to, f"Update on your claim {claim_id}"
    msg.set_content(text)
    with smtplib.SMTP(host, int(os.getenv("SMTP_PORT", "587")), timeout=15) as s:
        s.starttls()
        if os.getenv("SMTP_USER"):
            s.login(os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD", ""))
        s.send_message(msg)


def deliver(reply_id: str, claim_id: str, to: str | None, text: str, approved: bool) -> dict:
    """Returns a status record; never raises for policy reasons, only records why nothing was sent."""
    if reply_id in _sent:
        return {**_sent[reply_id], "duplicate": True}
    m = mode()
    if not approved:
        return {"status": "not_approved", "mode": m, "delivered": False}
    if m == "dry_run":
        return {"status": "dry_run", "mode": m, "delivered": False}
    if not to or not allowed(to):
        return {"status": "destination_not_allowed", "mode": m, "delivered": False}
    try:
        (_webhook if m == "webhook" else _smtp)(claim_id, to, text)
    except Exception as e:                               # network/provider failure: report, don't pretend
        return {"status": "failed", "mode": m, "delivered": False, "error": f"{type(e).__name__}: {e}"[:200]}
    rec = {"status": "sent", "mode": m, "delivered": True}
    _sent[reply_id] = rec
    return rec
