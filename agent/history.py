"""Claimant history for repeat-claim detection (in-memory; swap for a DB in production)."""
import time
from collections import defaultdict

WINDOW_DAYS = 30
REPEAT_AT = 3           # this many prior claims inside the window marks a repeat claimant
_claims: dict[str, list[float]] = defaultdict(list)


def record(customer_id: str | None, ts: float | None = None):
    if customer_id:
        _claims[customer_id].append(ts if ts is not None else time.time())


def prior_count(customer_id: str | None, now: float | None = None) -> int:
    if not customer_id:
        return 0
    now = now if now is not None else time.time()
    return sum(1 for t in _claims[customer_id] if now - t <= WINDOW_DAYS * 86400)


def is_repeat(customer_id: str | None, now: float | None = None) -> bool:
    return prior_count(customer_id, now) >= REPEAT_AT
