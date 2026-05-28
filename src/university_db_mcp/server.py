"""FastMCP server (stdio) exposing the university DB — the only component with DB access.

stdio transport: the client (agent) spawns this program as a subprocess and exchanges
JSON-RPC over stdin/stdout. "Server" is the MCP server *role*, not a network server.

Identity-per-call model: the server is identity-stateless. Each tool call carries the
`user_id`, so a single server instance serves all users and is discovered once at startup
(standard MCP binding) — no per-user subprocess. The same code works unchanged over an HTTP
transport for a long-running multi-user deployment.

Security invariant: `user_id` is supplied by the trusted agent from the authenticated
session — NEVER by the LLM. The agent injects it; the LLM only ever generates `sql`. The
server therefore trusts the asserted `user_id`, which in production requires an
authenticated agent→server channel (service token / mTLS).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from sqlalchemy import Engine

from university_db.engine import make_engine
from university_db_mcp.service import (
    EXAMPLE_QUERIES,
    AccessibleSchema,
    query_for_user,
    schema_for_user,
)


@dataclass
class ServerContext:
    """Lifespan state shared by every tool call."""

    engine: Engine  # one shared read-only engine; identity is per-call, not per-connection


@asynccontextmanager
async def _lifespan(_server: FastMCP) -> AsyncIterator[ServerContext]:
    """Build the shared read-only engine once and expose it for the server's lifetime."""
    yield ServerContext(engine=make_engine(read_only=True))


mcp = FastMCP("university-db", lifespan=_lifespan)


def _engine(ctx: Context) -> Engine:
    """Pull the shared engine out of the request's lifespan context."""
    return ctx.request_context.lifespan_context.engine


@mcp.tool()
def get_accessible_schema(user_id: str, ctx: Context) -> AccessibleSchema:
    """Return the relations and columns the given user may query (scoped to their role)."""
    return schema_for_user(_engine(ctx), user_id)


@mcp.tool()
def execute_sql(user_id: str, sql: str, ctx: Context) -> dict[str, Any]:
    """Run a read-only SQL query as the given user; returns rows or a structured rejection.

    `user_id` is injected by the trusted agent (authenticated session), not by the LLM.
    """
    return query_for_user(_engine(ctx), user_id, sql)


@mcp.resource("db://examples")
def examples() -> str:
    """Example SQL queries (identity-independent), including the percentile pattern."""
    return EXAMPLE_QUERIES


def main() -> None:
    """Console-script entry point: run the FastMCP server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
