"""Offline transport checks; no game projects, model calls or screen captures."""
import asyncio
import contextlib
import importlib.util
import io
import os
import socket
import sys
import tempfile
import unittest
from datetime import timedelta
from unittest.mock import patch

HAS_MCP = importlib.util.find_spec("mcp") is not None
if HAS_MCP:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from mcp.server.fastmcp import FastMCP
    import uvicorn


@unittest.skipUnless(HAS_MCP, "Install the project with .[mcp] to run protocol checks")
class MCPProtocolTests(unittest.IsolatedAsyncioTestCase):
    @contextlib.asynccontextmanager
    async def client(self, module, *args):
        params = StdioServerParameters(
            command=sys.executable, args=["-m", module, *args],
            env={**os.environ, "MCP_HTTP_HEADERS_JSON": "{}"},
        )
        with tempfile.TemporaryFile(mode="w+") as stderr:
            async with stdio_client(params, errlog=stderr) as streams:
                async with ClientSession(*streams, read_timeout_seconds=timedelta(seconds=15)) as client:
                    await client.initialize()
                    yield client

    async def test_screenshot_discovery_and_missing_project(self):
        async with self.client("gamedevbench.src.mcp_server") as client:
            listing = await client.list_tools()
            self.assertEqual([t.name for t in listing.tools], ["godot-screenshot"])
            with tempfile.TemporaryDirectory() as empty:
                result = await client.call_tool("godot-screenshot", {"project_dir": empty})
            self.assertIn("No project.godot", result.content[0].text)
            # An error must not break subsequent protocol messages.
            self.assertEqual(len((await client.list_tools()).tools), 1)

    async def test_screenshot_compression_leaves_stdout_clean(self):
        from PIL import Image
        from gamedevbench.src import mcp_server
        png, stdout = io.BytesIO(), io.StringIO()
        Image.new("RGB", (32, 32), "blue").save(png, format="PNG")
        with contextlib.redirect_stdout(stdout):
            data, mime = mcp_server.compress_screenshot(png.getvalue())
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(mime, "image/jpeg")
        self.assertEqual(Image.open(io.BytesIO(data)).size, (32, 32))

    async def test_http_bridge_roundtrip_and_excluded_tool(self):
        remote = FastMCP("local-test", stateless_http=True, json_response=True)

        @remote.tool(structured_output=True)
        def echo(value: int) -> dict[str, int]:
            return {"value": value}

        @remote.tool()
        def hidden() -> str:
            return "should not be called"

        @remote.tool()
        def fail() -> str:
            raise ValueError("fixture failure")

        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(remote.streamable_http_app(), log_level="critical"))
        task = asyncio.create_task(server.serve(sockets=[sock]))
        try:
            for _ in range(200):
                if server.started:
                    break
                if task.done():
                    await task
                    self.fail("HTTP fixture stopped before startup")
                await asyncio.sleep(0.025)
            self.assertTrue(server.started)
            async with self.client("godot_task_forge_mcp.http_stdio_bridge",
                                   "--url", f"http://127.0.0.1:{port}/mcp",
                                   "--exclude-tools", "hidden") as client:
                tools = await client.list_tools()
                self.assertEqual({t.name for t in tools.tools}, {"echo", "fail"})
                result = await client.call_tool("echo", {"value": 42})
                self.assertFalse(result.isError)
                self.assertEqual(result.structuredContent, {"value": 42})
                self.assertTrue((await client.call_tool("hidden", {})).isError)
                self.assertTrue((await client.call_tool("fail", {})).isError)
                self.assertFalse((await client.call_tool("echo", {"value": 7})).isError)
        finally:
            server.should_exit = True
            await asyncio.wait_for(task, timeout=10)
            sock.close()

    async def test_proxy_bypass_is_limited_to_loopback(self):
        from godot_task_forge_mcp.http_stdio_bridge import configure_local_proxy_bypass
        env = {"HTTP_PROXY": "http://proxy.example:8080", "NO_PROXY": "existing.example"}
        with patch.dict(os.environ, env, clear=True):
            configure_local_proxy_bypass("https://remote.example/mcp")
            self.assertEqual(dict(os.environ), env)
            configure_local_proxy_bypass("http://127.0.0.1:6601/mcp")
            self.assertEqual(os.environ["HTTP_PROXY"], env["HTTP_PROXY"])
            self.assertIn("existing.example", os.environ["NO_PROXY"])
            self.assertIn("127.0.0.1", os.environ["NO_PROXY"])
