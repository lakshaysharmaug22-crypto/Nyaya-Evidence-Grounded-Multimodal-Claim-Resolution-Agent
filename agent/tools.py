"""Tool registry with idempotency keys, retries and failure injection. Retries never double-execute."""
from typing import Callable

_REGISTRY: dict[str, Callable] = {}
_DONE: dict[str, dict] = {}
FAIL_ONCE: set[str] = set()          # "tool:idem_key" entries that fail on their first attempt (demo / tests)
EVENTS: dict[str, list] = {}         # idem_key -> trace events


class ToolError(Exception):
    pass


def tool(name: str):
    def wrap(fn):
        _REGISTRY[name] = fn
        return fn
    return wrap


def call(name: str, idem_key: str, retries: int = 2, **kwargs) -> dict:
    key = f"{name}:{idem_key}"
    ev = EVENTS.setdefault(idem_key, [])
    if key in _DONE:
        return _DONE[key]
    for attempt in range(retries + 1):
        try:
            if key in FAIL_ONCE:
                FAIL_ONCE.discard(key)
                raise ToolError(f"{name} unavailable")
            result = _REGISTRY[name](**kwargs)
            _DONE[key] = result
            ev.append({"tool": name, "attempt": attempt + 1, "ok": True})
            return result
        except ToolError as e:
            ev.append({"tool": name, "attempt": attempt + 1, "ok": False, "error": str(e)})
            if attempt == retries:
                raise
    raise ToolError(name)


@tool("order_lookup")
def order_lookup(order_id: str) -> dict:
    return {"order_id": order_id, "found": order_id.startswith("ORD"), "amount_inr": 1499.0}


@tool("issue_refund")
def issue_refund(order_id: str, amount_inr: float) -> dict:
    return {"order_id": order_id, "refunded_inr": amount_inr, "status": "issued"}


@tool("notify_customer")
def notify_customer(order_id: str, message: str) -> dict:
    return {"order_id": order_id, "sent": True}
