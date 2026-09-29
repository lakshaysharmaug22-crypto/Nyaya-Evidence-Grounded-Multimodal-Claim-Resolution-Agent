import sqlite3

import pytest
from langgraph.checkpoint.sqlite import SqliteSaver

from agent import graph as G
from agent import tools

CLAIM = {"order_id": "ORD1", "damage_conf": 0.95, "amount_inr": 1499, "days_since_delivery": 2,
         "text": "box was crushed and the item is broken"}


def saver(path):
    return SqliteSaver(sqlite3.connect(str(path), check_same_thread=False))


def cfg(i):
    return {"configurable": {"thread_id": i}}


@pytest.fixture(autouse=True)
def _isolate_idempotency(monkeypatch):
    monkeypatch.setattr(tools, "_db", None)
    yield


def test_crash_before_action_resumes_without_rerunning_earlier_steps(tmp_path):
    tools.use_sqlite(str(tmp_path / "idem.db"))
    g = G.build(saver(tmp_path / "cp.db"))
    G.CRASH_BEFORE_ACT.add("CK1")
    with pytest.raises(RuntimeError):
        g.invoke({"claim": {"id": "CK1", **CLAIM}}, cfg("CK1"))
    assert g.get_state(cfg("CK1")).next == ("n_act",)                 # stopped exactly where it crashed
    assert [e["tool"] for e in tools.EVENTS["CK1"]] == ["order_lookup"]

    g2 = G.build(saver(tmp_path / "cp.db"))                           # "new process": fresh graph, same files
    out = g2.invoke(None, cfg("CK1"))
    assert out["decision"]["decision"] == "approve" and out["action"]["status"] == "issued" and out["verified"]
    calls = [e["tool"] for e in tools.EVENTS["CK1"]]
    assert calls.count("order_lookup") == 1 and calls.count("issue_refund") == 1   # upstream steps were not repeated


def test_crash_after_refund_never_refunds_twice(tmp_path, monkeypatch):
    executed = []
    real = tools._REGISTRY["issue_refund"]
    monkeypatch.setitem(tools._REGISTRY, "issue_refund", lambda **kw: (executed.append(kw), real(**kw))[1])
    idem = str(tmp_path / "idem.db")
    tools.use_sqlite(idem)
    g = G.build(saver(tmp_path / "cp.db"))
    G.CRASH_AFTER_REFUND.add("CK2")
    with pytest.raises(RuntimeError):
        g.invoke({"claim": {"id": "CK2", **CLAIM}}, cfg("CK2"))
    assert len(executed) == 1                                         # refund went out before the crash

    tools._DONE.clear()                                               # process restart: memory is gone
    tools.use_sqlite(idem)                                            # ...but the idempotency store persisted
    out = G.build(saver(tmp_path / "cp.db")).invoke(None, cfg("CK2"))
    assert out["verified"] and out["action"]["status"] == "issued"
    assert len(executed) == 1                                         # the resumed action did NOT refund again


def test_without_persistent_store_a_restart_would_double_refund(tmp_path, monkeypatch):
    """Documents why use_sqlite matters: this is the failure the persistent store prevents."""
    executed = []
    real = tools._REGISTRY["issue_refund"]
    monkeypatch.setitem(tools._REGISTRY, "issue_refund", lambda **kw: (executed.append(kw), real(**kw))[1])
    g = G.build(saver(tmp_path / "cp.db"))
    G.CRASH_AFTER_REFUND.add("CK3")
    with pytest.raises(RuntimeError):
        g.invoke({"claim": {"id": "CK3", **CLAIM}}, cfg("CK3"))
    tools._DONE.clear()
    G.build(saver(tmp_path / "cp.db")).invoke(None, cfg("CK3"))
    assert len(executed) == 2


def test_finished_run_has_nothing_to_resume(tmp_path):
    g = G.build(saver(tmp_path / "cp.db"))
    g.invoke({"claim": {"id": "CK4", **CLAIM}}, cfg("CK4"))
    assert g.get_state(cfg("CK4")).next == ()


def test_idempotency_store_survives_restart(tmp_path):
    p = str(tmp_path / "i.db")
    tools.use_sqlite(p)
    tools.call("order_lookup", "persist-1", order_id="ORD9")
    tools._DONE.clear()
    tools.use_sqlite(p)
    n = len(tools.EVENTS["persist-1"])
    assert tools.call("order_lookup", "persist-1", order_id="ORD9")["found"]
    assert len(tools.EVENTS["persist-1"]) == n                        # served from the store, tool not called
