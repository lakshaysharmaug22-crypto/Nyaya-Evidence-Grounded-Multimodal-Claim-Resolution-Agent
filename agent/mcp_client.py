"""Load tools from any MCP server (stdio) into the agent's tool registry.

Each call runs in a worker thread with its own event loop, so it is safe to call from
synchronous graph nodes even when the API's event loop is running.
"""
import asyncio
import json
import sys
from concurrent.futures import ThreadPoolExecutor

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from . import tools

_pool = ThreadPoolExecutor(max_workers=1)


def _run(coro):
    return _pool.submit(asyncio.run, coro).result()


def _params(command: str, args: list[str]) -> StdioServerParameters:
    return StdioServerParameters(command=command, args=args)


def _unwrap(result) -> dict:
    if result.isError:
        text = result.content[0].text if result.content else "tool error"
        raise tools.ToolError(text)
    if result.structuredContent:
        return result.structuredContent
    return json.loads(result.content[0].text)


async def _list(params) -> list[str]:
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            return [t.name for t in (await s.list_tools()).tools]


async def _call(params, name: str, args: dict) -> dict:
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            return _unwrap(await s.call_tool(name, args))


def register_from_stdio(command: str = sys.executable, args: list[str] | None = None) -> list[str]:
    """Discover the server's tools and route the agent's registry entries through MCP."""
    params = _params(command, args or ["-m", "mcp_servers.support_tools"])
    names = _run(_list(params))
    for name in names:
        def make(n):
            def fn(**kwargs):
                try:
                    return _run(_call(params, n, kwargs))
                except tools.ToolError:
                    raise
                except Exception as e:                       # transport failure -> retryable
                    raise tools.ToolError(f"{n}: {type(e).__name__}: {e}")
            return fn
        tools._REGISTRY[name] = make(name)
    return names
