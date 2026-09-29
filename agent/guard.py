"""Deterministic guardrails around untrusted text and LLM output."""
import re

# Instruction-like phrases in customer text. Cheap, explainable, and checked before any model sees the text.
_INJECTION = [
    r"ignore (all |any |the |your )?(previous |prior |above )?(instructions|rules|policy|policies)",
    r"disregard (all |any |the |your )?(previous |prior |above )?(instructions|rules|policy|policies)",
    r"(approve|refund|pay)\b.{0,40}\b(immediately|regardless|no matter|without (checking|review))",
    r"you are now\b",
    r"system prompt",
    r"</?\s*(system|assistant|instructions?)\s*>",
    r"override (the )?(policy|rules|decision)",
    r"act as (an? )?(admin|manager|agent)",
]
_RX = [re.compile(p, re.I | re.S) for p in _INJECTION]


def looks_like_injection(text: str | None) -> bool:
    return bool(text) and any(rx.search(text) for rx in _RX)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def is_grounded(quote: str, source_text: str) -> bool:
    """A quote is grounded only if it appears verbatim (ignoring case and whitespace) in its source."""
    q = _norm(quote or "")
    return 3 <= len(q) <= 240 and q in _norm(source_text or "")
