"""Check a built Claude Code package and exercise its local MCP server."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import tempfile
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def verify_files(plugin: Path) -> dict:
    plugin = plugin.resolve(strict=True)
    manifest = json.loads((plugin / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    config = json.loads((plugin / ".mcp.json").read_text(encoding="utf-8"))
    inventory = json.loads((plugin / "audit/claude-files.json").read_text(encoding="utf-8"))
    if manifest["name"] != "archrivet" or set(config["mcpServers"]) != {"archrivet"}:
        raise ValueError("Unexpected plugin identity or MCP server")
    server = config["mcpServers"]["archrivet"]
    if server != {"type": "stdio", "command": "${CLAUDE_PLUGIN_ROOT}/runtime/python.exe",
                  "args": ["-I", "-B", "${CLAUDE_PLUGIN_ROOT}/launch.py"]}:
        raise ValueError("Unexpected MCP launch command")
    names = set()
    for entry in inventory["files"]:
        name = entry["path"]
        path = (plugin / name).resolve(strict=True)
        if name in names or not path.is_relative_to(plugin) or not path.is_file():
            raise ValueError(f"Unsafe or duplicate package path: {name}")
        if path.stat().st_size != entry["bytes"]:
            raise ValueError(f"Package size mismatch: {name}")
        h = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                h.update(chunk)
        if h.hexdigest() != entry["sha256"]:
            raise ValueError(f"Package hash mismatch: {name}")
        names.add(name)
    actual = {path.relative_to(plugin).as_posix() for path in plugin.rglob("*") if path.is_file()}
    if actual != names | {"audit/claude-files.json"}:
        raise ValueError("Package has missing or unexpected files")
    return manifest


def body(result) -> dict:
    value = result.model_dump(by_alias=True)
    if value.get("isError"):
        raise AssertionError("MCP tool reported an error")
    return value.get("structuredContent") or json.loads(result.content[0].text)


async def review(session, facts: dict) -> dict:
    request = {"input_mode": "supplied_facts", "requested_checks": ["cache_freshness"],
               "checks": [{"check_id": "cache_freshness", "scope_id": "catalogue",
                           "facts": facts,
                           "fact_origins": {key: "user_declared" for key in facts}}]}
    result = body(await session.call_tool("review_design", {"request": request}))
    for _ in range(100):
        if result["status"] == "completed":
            return result
        if result["status"] not in {"queued", "running"}:
            raise AssertionError("Review failed")
        await asyncio.sleep(.05)
        result = body(await session.call_tool("get_review", {"job_id": result["job_id"]}))
    raise TimeoutError("Review did not complete")


async def validate(plugin: Path) -> dict:
    plugin = plugin.resolve(strict=True)
    manifest = verify_files(plugin)
    with tempfile.TemporaryDirectory(prefix="archrivet-claude-test-") as home:
        params = StdioServerParameters(
            command=str(plugin / "runtime/python.exe"),
            args=["-I", "-B", str(plugin / "launch.py")], cwd=str(plugin),
            env={"USERPROFILE": home,
                 "PATH": os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32"),
                 "ARCHRIVET_ENABLE_LAYA": "true", "PYTHONPATH": "ignore-me"})
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer, read_timeout_seconds=30) as session:
                initialized = await session.initialize()
                if initialized.server_info.version != manifest["version"]:
                    raise AssertionError("Server and plugin versions differ")
                tools = {tool.name for tool in (await session.list_tools()).tools}
                required = {"get_review_schema", "review_design", "get_review", "compare_reviews",
                            "preview_proposal",
                            "create_architecture_view", "update_architecture_view"}
                if not required.issubset(tools):
                    raise AssertionError("Required review or diagram tools are missing")
                schema = body(await session.call_tool("get_review_schema", {}))
                if len(schema["decisions"]) != 8:
                    raise AssertionError("Unexpected decision schema")
                setup = body(await session.call_tool("get_setup_status", {}))
                if setup["variant"] != "rules" or setup["setup"]["worker_loaded"]:
                    raise AssertionError("This preview must use rules only")
                missing = await review(session, {"max_staleness_ms": 5000})
                missing_check = missing["result"]["checks"][0]
                if (missing_check["verdict"] != "insufficient_information"
                        or not missing_check["missing_information"]):
                    raise AssertionError("Missing information was not named")
                clarified = await review(session, {"max_staleness_ms": 5000,
                    "worst_case_staleness_ms": 4000, "bound_covers_failures": True,
                    "stale_on_error": False})
                if clarified["result"]["checks"][0]["verdict"] != "supported":
                    raise AssertionError("Clarified case did not change verdict")
                preview = body(await session.call_tool("preview_proposal", {"request": {"checks": [{
                    "check_id": "ack_durability", "scope_id": "orders", "facts": {
                        "requirements": {"acknowledged_operation": "order durably stored",
                                         "survive_failures": ["host_loss"]},
                        "design": {"acknowledgement": {"acknowledged_operation": "order durably stored",
                            "after_durable_commit": True, "survives_failures": ["host_loss"]}},
                }}]}}))
                if (preview["checks"][0]["conditional_verdict"] != "supported"
                        or preview["deployment_verified"] or preview["facts_verified"] or preview["model_used"]):
                    raise AssertionError("Proposed facts were presented as verified")
                compared = body(await session.call_tool("compare_reviews", {
                    "before_job_id": missing["job_id"], "after_job_id": clarified["job_id"]}))
                if not compared:
                    raise AssertionError("Comparison result missing")
                return {"status": "passed", "plugin_version": manifest["version"],
                        "tool_count": len(tools), "decision_count": len(schema["decisions"]),
                        "missing_verdict": missing_check["verdict"],
                        "clarified_verdict": clarified["result"]["checks"][0]["verdict"],
                        "proposal_conditional_verdict": preview["checks"][0]["conditional_verdict"],
                        "model_loaded": False, "claude_host_tested": False,
                        "publication_performed": False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plugin", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(validate(args.plugin)), indent=2))


if __name__ == "__main__":
    main()
