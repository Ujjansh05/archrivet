"""Submission hints must describe the tools actually exposed and their effects."""
import asyncio
import importlib.util
import json
from pathlib import Path

import pytest

from arch_review.diagram import RevisionConflict, ViewerManager
from arch_review.mcp_server import create_server as create_cli_server

ROOT = Path(__file__).resolve().parents[1]
HINTS = ("readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint")
DIAGRAM_HINTS = {
    "create_architecture_view": (False, True, False, False),
    "update_architecture_view": (False, True, True, False),
    "get_architecture_view": (True, False, True, False),
    "open_architecture_view": (False, False, False, False),
    "close_architecture_view": (False, True, False, False),
}
REMOTE_HINTS = {
    "get_review_schema": (True, False, True, False),
    "review_architecture": (True, False, True, False),
    "review_design": (False, False, False, False),
    "preview_proposal": (True, False, True, False),
    "get_review": (True, False, True, False),
    "cancel_review": (False, True, True, False),
    "compare_reviews": (True, False, True, False),
}


@pytest.fixture
def desktop_factory(tmp_path, monkeypatch):
    directory = ROOT / "extensions" / "desktop" / "server"
    monkeypatch.syspath_prepend(str(directory))
    spec = importlib.util.spec_from_file_location("archrivet_submission_annotations", directory / "main.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    instances = []

    def create(variant="rules", max_views=8):
        views = ViewerManager(max_views=max_views)
        monkeypatch.setattr(module, "ViewerManager", lambda: views)
        extension = module.Extension(tmp_path / str(len(instances)), variant=variant)
        server = module.create_server(extension)
        instances.append((extension, views))
        return server, extension, views

    yield create
    for extension, views in instances:
        views.shutdown()
        extension.close()


def hint_values(tool):
    assert tool.description, f"Missing description: {tool.name}"
    assert tool.annotations is not None, f"Missing annotations: {tool.name}"
    values = tool.annotations.model_dump(by_alias=True)
    assert all(type(values.get(key)) is bool for key in HINTS), tool.name
    return tuple(values[key] for key in HINTS)


def payload(result):
    body = result.model_dump(by_alias=True)
    assert not body.get("isError", False), "Tool failed; private response omitted"
    return body.get("structuredContent") or json.loads(result.content[0].text)


@pytest.mark.parametrize("variant", ["rules", "laya-cpu"])
async def test_all_desktop_tools_declare_effects_for_the_actual_bundle(desktop_factory, variant):
    server, extension, _ = desktop_factory(variant)
    internet_capable = variant == "laya-cpu"
    expected = {
        **DIAGRAM_HINTS,
        "get_setup_status": (True, False, True, False),
        "retry_model_setup": (not internet_capable, internet_capable, not internet_capable, internet_capable),
        "cancel_model_setup": (not internet_capable, internet_capable, True, False),
        "get_review_schema": (True, False, True, False),
        "preview_proposal": (True, False, True, False),
        "review_design": (False, internet_capable, False, internet_capable),
        "get_review": (True, False, True, False),
        "cancel_review": (False, True, True, False),
        "compare_reviews": (True, False, True, False),
    }
    tools = await server.list_tools()
    assert {tool.name: hint_values(tool) for tool in tools} == expected
    assert extension.setup.thread is None
    assert extension.backend is None


async def test_shared_viewer_annotations_are_also_exposed_by_cli():
    tools = await create_cli_server().list_tools()
    assert {tool.name: hint_values(tool) for tool in tools if tool.name in DIAGRAM_HINTS} == DIAGRAM_HINTS


async def test_remote_mcp_tools_declare_all_submission_hints():
    tools = await create_cli_server(include_viewer=False).list_tools()
    assert {tool.name: hint_values(tool) for tool in tools} == REMOTE_HINTS


async def test_viewer_effects_match_write_replacement_and_retry_hints(desktop_factory, monkeypatch):
    server, _, views = desktop_factory(max_views=2)
    launches = []
    monkeypatch.setattr(views, "_launch", lambda url: launches.append(url) or False)
    graph = {"title": "Catalog", "nodes": [{"id": "api", "label": "API"}]}
    first = payload(await server.call_tool("create_architecture_view", {"diagram": graph}))
    second = payload(await server.call_tool("create_architecture_view", {"diagram": graph}))
    assert first["view_id"] != second["view_id"]  # Creation is not idempotent.
    assert launches == []

    changed = {**graph, "title": "Catalog with cache"}
    updated = payload(await server.call_tool("update_architecture_view", {
        "view_id": first["view_id"], "diagram": changed, "expected_revision": 1}))
    assert updated["revision"] == 2
    assert views.get(first["view_id"])["diagram"]["title"] == changed["title"]
    with pytest.raises(RevisionConflict):
        views.update(first["view_id"], changed, 1)
    assert views.get(first["view_id"])["revision"] == 2  # Same-input retries cannot rewrite again.

    for _ in range(2):
        await server.call_tool("open_architecture_view", {"view_id": first["view_id"]})
    assert len(launches) == 2  # Opening is not idempotent even for an already active view.
    closed = payload(await server.call_tool("close_architecture_view", {"view_id": first["view_id"]}))
    assert closed["active"] is False
    await server.call_tool("create_architecture_view", {"diagram": graph})
    with pytest.raises(KeyError):
        views.get(first["view_id"])  # Creating at capacity evicts closed view data.


async def test_rules_setup_stays_local_and_duplicate_review_calls_queue_new_jobs(desktop_factory, monkeypatch):
    server, extension, _ = desktop_factory()

    def forbid_download():
        pytest.fail("Rules tools must not install model files")

    monkeypatch.setattr(extension.setup, "_install", forbid_download)
    status = payload(await server.call_tool("retry_model_setup", {}))
    assert status["status"] == "not_requested"
    request = {"input_mode": "supplied_facts", "checks": [{"check_id": "cache_freshness", "facts": {}}],
               "requested_checks": ["cache_freshness"]}
    first = payload(await server.call_tool("review_design", {"request": request}))
    second = payload(await server.call_tool("review_design", {"request": request}))
    assert first["job_id"] != second["job_id"]
    for submitted in (first, second):
        async with asyncio.timeout(10):
            job = submitted
            while job["status"] in {"queued", "running"}:
                await asyncio.sleep(.01)
                job = payload(await server.call_tool("get_review", {"job_id": job["job_id"]}))
        assert job["status"] == "completed"
        assert job["result"]["checks"][0]["verdict"] == "insufficient_information"
    assert extension.setup.thread is None
    assert extension.backend is None
