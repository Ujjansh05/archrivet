"""Verify that the private MCP endpoint actually runs the trained Laya model."""

import argparse
import asyncio
import json
from pathlib import Path

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


def body(result):
    data = result.model_dump(by_alias=True)
    if data.get("isError"):
        raise AssertionError(data)
    return data.get("structuredContent") or json.loads(result.content[0].text)


async def validate(url):
    async with streamable_http_client(url, terminate_on_close=False) as (reader, writer):
        async with ClientSession(reader, writer, read_timeout_seconds=220) as session:
            await session.initialize()
            names = {tool.name for tool in (await session.list_tools()).tools}
            if not {"get_review_schema", "review_design", "get_review"} <= names:
                raise AssertionError("Missing review tools")
            facts = {
                "requirements": {"acknowledged_operation": "order durably stored", "survive_failures": ["host_loss"]},
                "design": {"acknowledgement": {"acknowledged_operation": "enqueued in memory",
                                               "after_durable_commit": False, "survives_failures": []}},
            }
            origins = {
                "requirements.acknowledged_operation": "user_declared",
                "requirements.survive_failures": "user_declared",
                "design.acknowledgement.acknowledged_operation": "user_declared",
                "design.acknowledgement.after_durable_commit": "user_declared",
                "design.acknowledgement.survives_failures": "user_declared",
            }
            request = {"input_mode": "supplied_facts", "requested_checks": ["ack_durability"],
                       "checks": [{"check_id": "ack_durability", "scope_id": "orders",
                                   "facts": facts, "fact_origins": origins}]}
            result = body(await session.call_tool("review_design", {"request": request}))
            for _ in range(300):
                if result["status"] == "completed":
                    break
                if result["status"] not in {"queued", "running"}:
                    raise AssertionError("Review failed: " + repr(result))
                await asyncio.sleep(1)
                result = body(await session.call_tool("get_review", {"job_id": result["job_id"]}))
            else:
                raise TimeoutError("Laya review exceeded five minutes")
            review = result["result"]
            finding = review["checks"][0]
            if review["backend"]["name"] != "laya" or finding["model_decision"] is None:
                raise AssertionError("No Laya model judgment was returned: " + repr(review["coverage"]["inference_errors"]))
            if finding["verdict"] != "contradicted":
                raise AssertionError("Explicit in-memory acknowledgement was not contradicted")
            return {"status": "passed", "backend": review["backend"]["name"],
                    "rule_verdict": finding["rule_verdict"],
                    "model_verdict": finding["model_decision"]["verdict"],
                    "final_verdict": finding["verdict"],
                    "model_device": review["backend"].get("active_device"),
                    "inference_errors": review["coverage"]["inference_errors"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8767")
    args = parser.parse_args()
    secret = (args.directory / "secret.txt").read_text(encoding="ascii").strip()
    url = args.base_url.rstrip("/") + "/" + secret + "/mcp"
    print(json.dumps(asyncio.run(validate(url)), indent=2))


if __name__ == "__main__":
    main()
