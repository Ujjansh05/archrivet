"""Check the tunnel test server using real Streamable HTTP MCP requests."""

import argparse
import asyncio
import json
from pathlib import Path

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


def body(result):
    data = result.model_dump(by_alias=True)
    if data.get("isError"):
        raise AssertionError("ArchRivet tool returned an error")
    return data.get("structuredContent") or json.loads(result.content[0].text)


async def validate(url):
    async with streamable_http_client(url, terminate_on_close=False) as (reader, writer):
        async with ClientSession(reader, writer, read_timeout_seconds=30) as session:
            await session.initialize()
            names = {tool.name for tool in (await session.list_tools()).tools}
            if names != {"get_review_schema", "review_design", "get_review", "compare_reviews", "preview_proposal"}:
                raise AssertionError("Unexpected public tool surface: " + repr(sorted(names)))
            schema = body(await session.call_tool("get_review_schema", {}))
            if len(schema["decisions"]) != 8:
                raise AssertionError("Expected eight scoped checks")
            if "proposal_input" not in schema:
                raise AssertionError("Missing hypothetical proposal schema")
            def declared_paths(values, prefix=""):
                result = {}
                for key, value in values.items():
                    path = prefix + key
                    if isinstance(value, dict):
                        result.update(declared_paths(value, path + "."))
                    elif value is not None:
                        result[path] = "user_declared"
                return result
            def request(check_id, facts):
                return {"input_mode": "supplied_facts", "requested_checks": [check_id],
                        "checks": [{"check_id": check_id, "scope_id": "catalogue",
                                    "facts": facts,
                                    "fact_origins": declared_paths(facts)}]}
            async def review(check_id, facts):
                result = body(await session.call_tool("review_design", {"request": request(check_id, facts)}))
                for _ in range(120):
                    if result["status"] == "completed":
                        return result
                    if result["status"] not in {"queued", "running"}:
                        raise AssertionError("Review did not complete: " + repr(result))
                    await asyncio.sleep(.05)
                    result = body(await session.call_tool("get_review", {"job_id": result["job_id"]}))
                raise TimeoutError("Review timed out")
            first = await review("cache_freshness", {"max_staleness_ms": 5000})
            second = await review("cache_freshness", {"max_staleness_ms": 5000,
                                                       "worst_case_staleness_ms": 4000,
                                                       "bound_covers_failures": True,
                                                       "stale_on_error": False})
            before = first["result"]["checks"][0]
            after = second["result"]["checks"][0]
            if (before["verdict"] != "insufficient_information" or not before["missing_information"]
                    or after["verdict"] != "supported"):
                raise AssertionError("Verdicts or missing details were incorrect")
            body(await session.call_tool("compare_reviews", {
                "before_job_id": first["job_id"], "after_job_id": second["job_id"]}))
            ack = await review("ack_durability", {
                "requirements": {"acknowledged_operation": "order durably stored",
                                 "survive_failures": ["host_loss"]},
                "design": {"acknowledgement": {"acknowledged_operation": "enqueued in memory",
                                               "after_durable_commit": False,
                                               "survives_failures": []}}})
            ack_verdict = ack["result"]["checks"][0]["verdict"]
            if ack_verdict != "contradicted":
                raise AssertionError("Explicit early acknowledgement must be contradicted")
            preview = body(await session.call_tool("preview_proposal", {"request": {"checks": [{
                "check_id": "ack_durability", "scope_id": "orders", "facts": {
                    "requirements": {"acknowledged_operation": "order durably stored",
                                     "survive_failures": ["host_loss"]},
                    "design": {"acknowledgement": {"acknowledged_operation": "order durably stored",
                        "after_durable_commit": True, "survives_failures": ["host_loss"]}},
            }}]}}))
            if (preview["checks"][0]["conditional_verdict"] != "supported"
                    or preview["deployment_verified"] or preview["facts_verified"] or preview["model_used"]):
                raise AssertionError("Proposal preview promoted assumptions into verified facts")
            return {"status": "passed", "transport": "streamable-http-json",
                    "tool_count": len(names), "decision_count": len(schema["decisions"]),
                    "missing_verdict": before["verdict"], "clarified_verdict": after["verdict"],
                    "early_ack_verdict": ack_verdict,
                    "proposal_conditional_verdict": preview["checks"][0]["conditional_verdict"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    args = parser.parse_args()
    secret = (args.directory / "secret.txt").read_text(encoding="ascii").strip()
    url = args.base_url.rstrip("/") + "/" + secret + "/mcp"
    print(json.dumps(asyncio.run(validate(url)), indent=2))


if __name__ == "__main__":
    main()
