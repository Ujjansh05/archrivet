"""Live viewer tools over real stdio, with no model or review daemon running."""
import asyncio
import json
import os
import socket
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
VIEWER_TOOLS = {
    "create_architecture_view", "update_architecture_view", "get_architecture_view",
    "open_architecture_view", "close_architecture_view",
}


def graph(*, queue=False):
    value = {"title": "Order processing", "nodes": [
        {"id": "browser", "label": "Customer", "kind": "client", "state": "existing"},
        {"id": "api", "label": "Order API", "kind": "service", "state": "proposed"},
    ], "edges": [{"id": "submit", "source": "browser", "target": "api", "label": "Place order"}]}
    if queue:
        value["nodes"].append({"id": "emails", "label": "Email queue", "kind": "queue", "state": "proposed"})
        value["edges"].append({"id": "schedule", "source": "api", "target": "emails", "label": "Order email"})
    return value


def payload(result):
    # Do not include the tool result in failure output: create/get contain a private URL.
    body = result.model_dump(by_alias=True)
    if body.get("isError", False):
        raise AssertionError("Viewer tool returned an MCP error; private response omitted")
    return body.get("structuredContent") or json.loads(result.content[0].text)


@asynccontextmanager
async def session_at(directory):
    directory.mkdir(parents=True)
    guard = directory / "import-guard"
    guard.mkdir()
    # Fail if creating/listing diagrams imports a model. Record browser launches
    # without opening a real window during protocol tests.
    (guard / "sitecustomize.py").write_text('''import importlib.abc, os, sys, webbrowser
from pathlib import Path
class NoModelImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'torch', 'laya', 'transformers', 'numpy', 'safetensors'}:
            raise AssertionError('Viewer imported a model library')
sys.meta_path.insert(0, NoModelImports())
def no_browser(*args, **kwargs):
    Path(os.environ['ARCHRIVET_TEST_BROWSER_MARKER']).write_text('called')
    return False
webbrowser.open = no_browser
''', encoding="utf-8")
    parameters = StdioServerParameters(command=sys.executable, args=["-m", "arch_review", "mcp"], env={
        "ARCH_REVIEW_HOME": str(directory / "empty-runtime"),
        "PYTHONPATH": os.pathsep.join((str(guard), str(ROOT / "src"))),
        "ARCHRIVET_TEST_BROWSER_MARKER": str(directory / "browser-opened"),
    })
    async with stdio_client(parameters) as (reader, writer):
        async with ClientSession(reader, writer, read_timeout_seconds=30) as session:
            await session.initialize()
            yield session
    assert not (directory / "browser-opened").exists(), "A closed viewer was unexpectedly reopened"


def connection_info(created):
    address = urlsplit(created["url"])
    fragment = parse_qs(address.fragment)
    assert address.scheme == "http"
    assert address.hostname == "127.0.0.1"
    assert not address.query, "Viewer credentials must stay out of HTTP query strings"
    assert set(fragment) == {"view", "token"}
    return address, fragment["view"][0], {"Authorization": "Bearer " + fragment["token"][0]}


async def listener_has_stopped(port):
    deadline = asyncio.get_running_loop().time() + 5
    while True:
        with socket.socket() as connection:
            connection.settimeout(.2)
            stopped = connection.connect_ex(("127.0.0.1", port)) != 0
        if stopped:
            return
        if asyncio.get_running_loop().time() >= deadline:
            raise AssertionError("The viewer listener survived the MCP session")
        await asyncio.sleep(.05)


async def test_stdio_viewer_changes_stale_revisions_and_independent_close(tmp_path):
    async with session_at(tmp_path / "session") as session:
        names = {tool.name for tool in (await session.list_tools()).tools}
        assert VIEWER_TOOLS <= names
        prompts = await session.list_prompts()
        assert "design_with_diagram" in {prompt.name for prompt in prompts.prompts}
        created = payload(await session.call_tool("create_architecture_view", {
            "diagram": graph(), "open_browser": False}))
        assert created["revision"] == 1
        assert created["active"] is True
        assert created["browser_opened"] is False
        address, view_id, headers = connection_info(created)
        base = f"{address.scheme}://{address.netloc}"
        async with httpx.AsyncClient(base_url=base, trust_env=False, timeout=3) as client:
            denied = await client.get("/api/state", params={"view": view_id})
            assert denied.status_code == 401
            response = await client.get("/api/state", params={"view": view_id}, headers=headers)
            assert response.status_code == 200
            state = response.json()
            assert state["revision"] == 1
            assert state["diagram"]["title"] == "Order processing"
            assert "url" not in state and "token" not in state

            updated = payload(await session.call_tool("update_architecture_view", {
                "view_id": view_id, "diagram": graph(queue=True), "expected_revision": 1}))
            assert updated["revision"] == 2
            assert updated["changes"]["added_nodes"] == ["emails"]
            assert updated["changes"]["added_edges"] == ["schedule"]
            stale = await session.call_tool("update_architecture_view", {
                "view_id": view_id, "diagram": graph(), "expected_revision": 1})
            assert stale.model_dump(by_alias=True).get("isError") is True
            current = payload(await session.call_tool("get_architecture_view", {"view_id": view_id}))
            assert current["revision"] == 2
            assert len(current["diagram"]["nodes"]) == 3

            closed = payload(await session.call_tool("close_architecture_view", {"view_id": view_id}))
            assert closed["active"] is False
            updated_closed = payload(await session.call_tool("update_architecture_view", {
                "view_id": view_id, "diagram": graph(), "expected_revision": 2}))
            assert updated_closed["active"] is False
            assert updated_closed["revision"] == 3
            response = await client.get("/api/state", params={"view": view_id}, headers=headers)
            assert response.status_code == 200
            assert response.json()["active"] is False
            assert response.json()["revision"] == 3
            # Diagram close must leave the assistant's ordinary tools responsive.
            schema = payload(await session.call_tool("get_review_schema", {}))
            assert len(schema["decisions"]) == 8
    await listener_has_stopped(address.port)


async def test_stdio_viewers_are_private_to_each_assistant_session(tmp_path):
    async with session_at(tmp_path / "first") as first:
        async with session_at(tmp_path / "second") as second:
            a = payload(await first.call_tool("create_architecture_view", {
                "diagram": graph(), "open_browser": False}))
            b = payload(await second.call_tool("create_architecture_view", {
                "diagram": graph(queue=True), "open_browser": False}))
            address_a, view_a, auth_a = connection_info(a)
            address_b, view_b, auth_b = connection_info(b)
            assert address_a.port != address_b.port
            unavailable = await second.call_tool("get_architecture_view", {"view_id": view_a})
            assert unavailable.model_dump(by_alias=True).get("isError") is True
            unavailable = await first.call_tool("close_architecture_view", {"view_id": view_b})
            assert unavailable.model_dump(by_alias=True).get("isError") is True
            async with httpx.AsyncClient(trust_env=False, timeout=3) as client:
                base_b = f"http://127.0.0.1:{address_b.port}"
                wrong_token = await client.get(base_b + "/api/state", params={"view": view_b}, headers=auth_a)
                assert wrong_token.status_code == 401
                own_token = await client.get(base_b + "/api/state", params={"view": view_b}, headers=auth_b)
                assert own_token.status_code == 200
                assert own_token.json()["active"] is True
        await listener_has_stopped(address_b.port)
        current = payload(await first.call_tool("get_architecture_view", {"view_id": view_a}))
        assert current["active"] is True
        assert current["revision"] == 1
    await listener_has_stopped(address_a.port)
