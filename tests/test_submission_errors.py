"""Expected MCP failures give recovery steps without echoing private input."""
import asyncio
import importlib.util
import json
import sys
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.server.mcpserver.exceptions import ToolError, UnexpectedToolError

from arch_review.diagram import ViewerManager

ROOT = Path(__file__).resolve().parents[1]
DESKTOP = ROOT / "extensions" / "desktop" / "server"
GRAPH = {"title": "Catalog", "nodes": [{"id": "api", "label": "API"}]}
REQUEST = {"input_mode": "supplied_facts", "checks": [{"check_id": "cache_freshness", "facts": {}}],
           "requested_checks": ["cache_freshness"]}


@pytest.fixture
def desktop(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(DESKTOP))
    spec = importlib.util.spec_from_file_location("archrivet_submission_errors", DESKTOP / "main.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    views = ViewerManager(max_views=1)
    monkeypatch.setattr(module, "ViewerManager", lambda: views)
    extension = module.Extension(tmp_path, variant="rules")
    yield module.create_server(extension), extension, views
    views.shutdown()
    extension.close()


def payload(result):
    body = result.model_dump(by_alias=True)
    assert not body.get("isError", False), "Tool failed; private response omitted"
    return body.get("structuredContent") or json.loads(result.content[0].text)


def error_text(result):
    assert result.model_dump(by_alias=True).get("isError") is True
    return " ".join(block.text for block in result.content if block.type == "text")


@pytest.mark.skipif(sys.platform != "win32", reason="Packaged stdio entry point supports Windows x64")
async def test_stdio_stale_revision_and_session_errors_explain_recovery(tmp_path):
    parameters = StdioServerParameters(command=sys.executable, args=[str(DESKTOP / "main.py")], env={
        "ARCHRIVET_EXTENSION_HOME": str(tmp_path), "ARCHRIVET_ENABLE_LAYA": "false",
        "PYTHONPATH": str(ROOT / "src"),
    })
    async with stdio_client(parameters) as (reader, writer):
        async with ClientSession(reader, writer, read_timeout_seconds=30) as session:
            await session.initialize()
            created = payload(await session.call_tool("create_architecture_view", {"diagram": GRAPH}))
            arguments = {"view_id": created["view_id"], "diagram": GRAPH, "expected_revision": 1}
            payload(await session.call_tool("update_architecture_view", arguments))
            message = error_text(await session.call_tool("update_architecture_view", arguments))
            assert "get_architecture_view" in message and "current revision" in message
            assert created["url"] not in message
            assert created["view_id"] not in message
            assert len(message) < 400
            malicious_id = "private-token-do-not-repeat"
            message = error_text(await session.call_tool("get_architecture_view", {"view_id": malicious_id}))
            assert "session" in message and malicious_id not in message

            job = payload(await session.call_tool("review_design", {"request": REQUEST}))
            for tool in ("get_review", "cancel_review"):
                invalid = error_text(await session.call_tool(tool, {"job_id": malicious_id}))
                assert "Invalid review ID" in invalid and "session" in invalid
                assert malicious_id not in invalid
                foreign = error_text(await session.call_tool(tool, {"job_id": "f" * 32}))
                assert "expired" in foreign and "session" in foreign and "review_design" in foreign
            foreign = error_text(await session.call_tool("compare_reviews", {
                "before_job_id": job["job_id"], "after_job_id": "f" * 32}))
            assert "expired" in foreign and "session" in foreign


async def test_viewer_limit_and_invalid_revision_are_expected_errors(desktop):
    server, _, _ = desktop
    created = payload(await server.call_tool("create_architecture_view", {"diagram": GRAPH}))
    with pytest.raises(ToolError, match="Close an existing view") as caught:
        await server.call_tool("create_architecture_view", {"diagram": GRAPH})
    assert not isinstance(caught.value, UnexpectedToolError)
    with pytest.raises(ToolError, match="positive integer.*get_architecture_view") as caught:
        await server.call_tool("update_architecture_view", {
            "view_id": created["view_id"], "diagram": GRAPH, "expected_revision": 0})
    assert not isinstance(caught.value, UnexpectedToolError)


async def test_closed_and_full_review_sessions_give_bounded_recovery(desktop):
    server, extension, _ = desktop
    job = payload(await server.call_tool("review_design", {"request": REQUEST}))
    async with asyncio.timeout(10):
        while job["status"] in {"queued", "running"}:
            await asyncio.sleep(.01)
            job = extension.get(job["job_id"])
    extension.jobs.max_pending = 0
    with pytest.raises(ToolError, match="No review was queued.*queue is full") as caught:
        await server.call_tool("review_design", {"request": REQUEST})
    assert not isinstance(caught.value, UnexpectedToolError)
    extension.closed = True
    with pytest.raises(ToolError, match="Reconnect the plugin") as caught:
        await server.call_tool("review_design", {"request": REQUEST})
    assert not isinstance(caught.value, UnexpectedToolError)


async def test_model_not_ready_keeps_clear_structured_status(desktop):
    server, extension, _ = desktop
    # Simulate an opted-in setup still checking, without loading/downloading a model.
    extension.setup.enabled = True
    extension.setup.update(status="checking")
    result = payload(await server.call_tool("review_design", {"request": REQUEST}))
    assert result["status"] == "setup_required"
    assert "no review has run" in result["message"]
    assert extension.jobs is None
    assert extension.setup.thread is None


@pytest.mark.parametrize("error_type", [ValueError, RuntimeError])
@pytest.mark.parametrize("target", ["viewer", "review"])
async def test_unexpected_exception_details_stay_masked(desktop, monkeypatch, error_type, target):
    server, extension, views = desktop
    secret = "private-design-and-token-must-not-be-returned"

    def fail(*_):
        raise error_type(secret)

    if target == "viewer":
        monkeypatch.setattr(views, "get", fail)
        tool, arguments = "get_architecture_view", {"view_id": "unknown"}
    else:
        monkeypatch.setattr(extension, "get", fail)
        tool, arguments = "get_review", {"job_id": "f" * 32}
    with pytest.raises(UnexpectedToolError) as caught:
        await server.call_tool(tool, arguments)
    assert secret not in str(caught.value)
    assert str(caught.value) == "Error executing tool " + tool
