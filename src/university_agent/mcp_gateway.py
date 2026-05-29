"""Gateway to the university MCP server via the standard langchain-mcp-adapters client.

The agent is a proper MCP *client*: it DISCOVERS the server's tools/resources at connect
rather than re-declaring them, so the MCP server can evolve without changing the graph or
its nodes. Nodes depend only on the small `Gateway` interface — a fake satisfies it for
tests, while the real implementation here wraps the discovered tools. `user_id` is supplied
by the graph on each call, never by the LLM.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Protocol

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.resources import load_mcp_resources
from langchain_mcp_adapters.tools import load_mcp_tools

SERVER_NAME = "university-db"
EXAMPLES_URI = "db://examples"


class Gateway(Protocol):
    """The interface graph nodes use; a fake implementing this is enough for tests."""

    async def get_schema(self, user_id: str) -> dict[str, Any]: ...
    async def execute_sql(self, user_id: str, sql: str) -> dict[str, Any]: ...
    async def get_examples(self) -> str: ...


def _parse(result: Any) -> dict[str, Any]:
    """Adapter tool results arrive as text content blocks; parse the JSON payload."""
    if isinstance(result, list) and result and isinstance(result[0], dict):
        return json.loads(result[0]["text"])
    if isinstance(result, str):
        return json.loads(result)
    return result  # already structured


@dataclass
class _Connected:
    tools: dict[str, BaseTool]
    session: Any

    async def get_schema(self, user_id: str) -> dict[str, Any]:
        return _parse(await self.tools["get_accessible_schema"].ainvoke({"user_id": user_id}))

    async def execute_sql(self, user_id: str, sql: str) -> dict[str, Any]:
        return _parse(await self.tools["execute_sql"].ainvoke({"user_id": user_id, "sql": sql}))

    async def get_examples(self) -> str:
        blobs = await load_mcp_resources(self.session, uris=[EXAMPLES_URI])
        return blobs[0].data


@asynccontextmanager
async def connect(db_url: str | None = None) -> AsyncIterator[_Connected]:
    """Spawn the MCP server, discover its tools/resources, and yield a gateway for one run.

    db_url is passed into the server's environment so the agent and server agree on the DB.
    """
    env = dict(os.environ)
    if db_url:
        env["DATABASE_URL"] = db_url
    client = MultiServerMCPClient(
        {
            SERVER_NAME: {
                "command": "uv",
                "args": ["run", "university-db-mcp"],
                "transport": "stdio",
                "env": env,
            }
        }
    )
    async with client.session(SERVER_NAME) as session:
        tools = {tool.name: tool for tool in await load_mcp_tools(session)}
        yield _Connected(tools=tools, session=session)
