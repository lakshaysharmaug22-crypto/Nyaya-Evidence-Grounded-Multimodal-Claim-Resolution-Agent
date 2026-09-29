import pytest
from agent import tools


def test_idempotent_no_double_execution():
    calls = []
    tools._REGISTRY["probe"] = lambda x: (calls.append(x), {"ok": 1})[1]
    tools.call("probe", "k1", x=1); tools.call("probe", "k1", x=1)
    assert len(calls) == 1

def test_retry_recovers_from_single_failure():
    tools.FAIL_ONCE.add("order_lookup:t-retry")
    r = tools.call("order_lookup", "t-retry", order_id="ORD1")
    assert r["found"]
    ev = tools.EVENTS["t-retry"]
    assert [e["ok"] for e in ev] == [False, True]

def test_gives_up_after_retries():
    def boom(): raise tools.ToolError("down")
    tools._REGISTRY["boom"] = boom
    with pytest.raises(tools.ToolError):
        tools.call("boom", "t-boom", retries=1)
    assert len(tools.EVENTS["t-boom"]) == 2
