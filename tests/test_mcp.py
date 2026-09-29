import pytest
from agent import tools, mcp_client


@pytest.fixture
def restore_registry():
    saved = dict(tools._REGISTRY)
    yield
    tools._REGISTRY.clear(); tools._REGISTRY.update(saved)


def test_server_lists_and_agent_calls_tools_over_mcp(restore_registry):
    names = mcp_client.register_from_stdio()
    assert set(names) == {"order_lookup", "issue_refund", "notify_customer"}
    r = tools.call("order_lookup", "mcp-1", order_id="ORD77")
    assert r["found"] is True and r["order_id"] == "ORD77"
    assert tools.call("issue_refund", "mcp-1", order_id="ORD77", amount_inr=499.0)["status"] == "issued"


def test_retry_and_idempotency_still_apply_over_mcp(restore_registry):
    mcp_client.register_from_stdio()
    tools.FAIL_ONCE.add("order_lookup:mcp-2")
    assert tools.call("order_lookup", "mcp-2", order_id="ORD1")["found"]
    assert [e["ok"] for e in tools.EVENTS["mcp-2"]] == [False, True]
    again = tools.call("order_lookup", "mcp-2", order_id="ORD1")
    assert again["found"] and len(tools.EVENTS["mcp-2"]) == 2      # cached, no new call
