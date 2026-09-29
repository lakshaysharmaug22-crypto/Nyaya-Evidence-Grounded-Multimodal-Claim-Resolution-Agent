"""MCP server exposing the support tools (order lookup, refund, customer notification).

Run over stdio:  python -m mcp_servers.support_tools
Any MCP client (this agent, Claude Desktop, other agent frameworks) can call these tools.
"""
from mcp.server.fastmcp import FastMCP

from agent import tools

mcp = FastMCP("support-tools")


@mcp.tool()
def order_lookup(order_id: str) -> dict:
    """Look up an order by ID. Returns whether it exists and its amount in INR."""
    return tools.order_lookup(order_id)


@mcp.tool()
def issue_refund(order_id: str, amount_inr: float) -> dict:
    """Issue a refund in INR for an order. Callers must pass an idempotency key at the agent layer."""
    return tools.issue_refund(order_id, amount_inr)


@mcp.tool()
def notify_customer(order_id: str, message: str) -> dict:
    """Send a status message to the customer for an order."""
    return tools.notify_customer(order_id, message)


if __name__ == "__main__":
    mcp.run()
