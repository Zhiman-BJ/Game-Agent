"""Bridge a configured MCP Streamable HTTP tool server to stdio.

Adapted from the experiment bridge. No deployment URL, credentials or
organization-specific headers are embedded in this module.
"""

import argparse
import asyncio
import json
import os
from contextlib import asynccontextmanager
from datetime import timedelta
from urllib.parse import urlsplit

from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, TextContent


def configure_local_proxy_bypass(url: str) -> None:
    """Bypass proxies for loopback only, preserving remote proxy settings."""
    if urlsplit(url).hostname not in {"127.0.0.1", "localhost", "::1"}:
        return
    for key in ("NO_PROXY", "no_proxy"):
        entries = [x for x in os.environ.get(key, "").split(",") if x]
        os.environ[key] = ",".join(dict.fromkeys(entries + ["127.0.0.1", "localhost", "::1"]))


class HttpToStdioBridge:
    def __init__(self, remote_url: str, timeout_seconds: int = 60,
                 exclude_tools: set[str] | None = None):
        self.remote_url = remote_url
        self.timeout_seconds = timeout_seconds
        self.exclude_tools = exclude_tools or set()
        self.headers = json.loads(os.environ.get("MCP_HTTP_HEADERS_JSON", "{}"))
        if not isinstance(self.headers, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in self.headers.items()
        ):
            raise ValueError("MCP_HTTP_HEADERS_JSON must be an object of string headers")
        self.server = Server("game-http-stdio-bridge")
        self.server.list_tools()(self.list_tools)
        self.server.call_tool()(self.call_tool)

    @asynccontextmanager
    async def remote_session(self):
        # Context managers close both transports on success, errors and cancellation.
        async with streamablehttp_client(url=self.remote_url, headers=self.headers) as streams:
            async with ClientSession(
                streams[0], streams[1],
                read_timeout_seconds=timedelta(seconds=self.timeout_seconds),
            ) as session:
                await session.initialize()
                yield session

    async def list_tools(self):
        async with self.remote_session() as session:
            tools, cursor, seen = [], None, set()
            while True:
                result = await session.list_tools(cursor=cursor)
                tools.extend(t for t in result.tools if t.name not in self.exclude_tools)
                cursor = result.nextCursor
                if not cursor:
                    return tools
                if cursor in seen:
                    raise RuntimeError("Remote server repeated a tools pagination cursor")
                seen.add(cursor)

    async def call_tool(self, name: str, arguments: dict):
        if name in self.exclude_tools:
            return CallToolResult(isError=True, content=[
                TextContent(type="text", text="Tool is excluded by bridge configuration")
            ])
        async with self.remote_session() as session:
            # Preserve structuredContent and isError, not just text/image content.
            return await session.call_tool(name, arguments or {})

    async def run(self):
        async with stdio_server() as streams:
            await self.server.run(*streams, self.server.create_initialization_options())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="MCP Streamable HTTP endpoint")
    parser.add_argument("--timeout", type=int, default=60, help="Remote read timeout in seconds")
    parser.add_argument("--exclude-tools", default="", help="Comma-separated tool names to omit and reject")
    args = parser.parse_args()
    if urlsplit(args.url).scheme not in {"http", "https"} or not urlsplit(args.url).hostname:
        parser.error("--url must be an HTTP(S) URL")
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    configure_local_proxy_bypass(args.url)
    asyncio.run(HttpToStdioBridge(args.url, args.timeout, {
        name.strip() for name in args.exclude_tools.split(",") if name.strip()
    }).run())


if __name__ == "__main__":
    main()
