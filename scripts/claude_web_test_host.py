"""ArchRivet Streamable HTTP MCP server for a private tunnel test.

Run with the Python runtime from the audited Windows plugin bundle. The random
URL path is a bearer secret: possession of the full URL grants review access.
"""

import argparse
import asyncio
import hmac
import json
import os
import secrets
import sys
from contextlib import asynccontextmanager
from pathlib import Path


def read_or_create_secret(directory: Path) -> str:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "secret.txt"
    if not path.exists():
        value = secrets.token_urlsafe(32)
        with path.open("x", encoding="ascii") as stream:
            stream.write(value + "\n")
    value = path.read_text(encoding="ascii").strip()
    if len(value) < 40 or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in value):
        raise ValueError("Invalid URL secret")
    return value


class SecretPathGate:
    """Expose one secret MCP path; reject other HTTP paths and browser origins."""

    def __init__(self, app, secret: str):
        self.app = app
        self.path = "/" + secret + "/mcp"

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {key.decode("ascii").lower(): value.decode("latin-1")
                   for key, value in scope.get("headers", [])}
        host = headers.get("host", "").lower().split(":", 1)[0]
        local = host in {"127.0.0.1", "localhost"}
        tunnel = host.endswith(".trycloudflare.com") and host.count(".") == 2
        origin = headers.get("origin")
        allowed_origin = origin is None or origin in {"https://claude.ai", f"https://{host}"}
        allowed = (local or tunnel) and allowed_origin and hmac.compare_digest(scope["path"], self.path)
        if not allowed:
            await send({"type": "http.response.start", "status": 404,
                        "headers": [(b"content-type", b"text/plain"), (b"cache-control", b"no-store")]})
            await send({"type": "http.response.body", "body": b"Not found"})
            return
        inner = dict(scope)
        inner["path"] = "/mcp"
        inner["raw_path"] = b"/mcp"
        inner["headers"] = [(key, value) for key, value in scope["headers"] if key.lower() != b"host"] + [
            (b"host", b"127.0.0.1")]
        await self.app(inner, receive, send)


def create_app(bundle: Path, directory: Path, secret: str, backend_name="rules", checkpoint=None):
    if backend_name == "laya":
        source = Path(__file__).resolve().parents[1] / "src"
        if not (source / "arch_review").is_dir():
            raise ValueError("ArchRivet source package is missing")
        if checkpoint is None or not (checkpoint / "rl_agent_config.json").is_file():
            raise ValueError("A complete local Laya checkpoint is required")
        sys.path.insert(0, str(source))
    else:
        site_packages = bundle / "runtime" / "Lib" / "site-packages"
        if not (site_packages / "arch_review").is_dir():
            raise ValueError("Extracted ArchRivet bundle is missing its reviewed engine")
        sys.path.insert(0, str(site_packages))
    import uvicorn
    from mcp.server import MCPServer
    from mcp.server.transport_security import TransportSecuritySettings
    from mcp.types import ToolAnnotations

    from arch_review.backends import LayaBackend, NoModelBackend
    from arch_review.evidence_v2 import PersistentEvidence
    from arch_review.jobs import ReviewJobs
    from arch_review.proposal import ProposalPreviewRequest
    from arch_review.proposal import preview_proposal as calculate_proposal_preview
    from arch_review.registry import definitions
    from arch_review.review_v2 import DesignReviewer
    from arch_review.schema_v2 import DesignReviewRequest

    if backend_name == "laya":
        from arch_review.model import ModelWorker
        from arch_review.settings import Settings
        backend = LayaBackend(ModelWorker(Settings(
            backend="laya", checkpoint=str(checkpoint), device="cpu", threads=4,
            model_context_tokens=2048, inference_timeout_seconds=180, idle_seconds=600)))
    else:
        backend = NoModelBackend()

    jobs = ReviewJobs(DesignReviewer(backend, PersistentEvidence(directory / "evidence-index")),
                      max_pending=2, ttl_seconds=900, review_timeout_seconds=300 if backend_name == "laya" else 120)

    @asynccontextmanager
    async def lifespan(_server):
        try:
            yield {}
        finally:
            await asyncio.to_thread(jobs.close)

    server = MCPServer("archrivet", title="ArchRivet private web test", version="0.4.0-alpha.1",
                       lifespan=lifespan, instructions=(
                           ("Experimental Laya model plus rules. Model judgments may be wrong; show disagreements. "
                            if backend_name == "laya" else "Rules-only test. ") +
                           "Call get_review_schema before review_design. Supply only stated facts; "
                           "Use preview_proposal for a conditional rules-only check of an assistant's suggested design. "
                           "leave unknowns unknown. Poll get_review. A supported narrow check is not production "
                           "certification. Workload arithmetic is demand, not measured capacity."))

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False,
                                              idempotentHint=True, openWorldHint=False))
    def get_review_schema() -> dict:
        """Get the eight scoped architecture checks and the exact review input schema."""
        return {"schema_version": "2.0", "input": DesignReviewRequest.model_json_schema(),
                "proposal_input": ProposalPreviewRequest.model_json_schema(),
                "decisions": definitions(), "verdicts": {
                    "supported": "Explicit supplied facts satisfy this narrow check.",
                    "contradicted": "Explicit supplied facts violate this requirement.",
                    "insufficient_information": "Required facts are missing, ambiguous or conflicting."}}

    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False,
                                              idempotentHint=False, openWorldHint=False))
    def review_design(request: DesignReviewRequest) -> dict:
        """Review supplied design facts. Return a job ID; poll get_review. No code execution or model download."""
        return jobs.submit(request)

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False,
                                              idempotentHint=True, openWorldHint=False))
    def preview_proposal(request: ProposalPreviewRequest) -> dict:
        """Conditionally check proposed design facts with rules; none are treated as deployed or verified."""
        return calculate_proposal_preview(request)

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False,
                                              idempotentHint=True, openWorldHint=False))
    def get_review(job_id: str) -> dict:
        """Read a bounded review job and its missing details, evidence and workload estimates."""
        if len(job_id) != 32 or any(c not in "0123456789abcdef" for c in job_id):
            raise ValueError("Invalid review ID")
        try:
            return jobs.get(job_id)
        except KeyError as exc:
            raise ValueError("Review expired or is unknown") from exc

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False,
                                              idempotentHint=True, openWorldHint=False))
    def compare_reviews(before_job_id: str, after_job_id: str) -> dict:
        """Compare two completed reviews and name the facts that changed the verdict."""
        if any(len(key) != 32 or any(c not in "0123456789abcdef" for c in key)
               for key in (before_job_id, after_job_id)):
            raise ValueError("Invalid review ID")
        try:
            return jobs.compare(before_job_id, after_job_id)
        except KeyError as exc:
            raise ValueError("Review expired or is unknown") from exc

    app = server.streamable_http_app(json_response=True, stateless_http=True,
                                     max_request_body_size=2 * 1024 * 1024,
                                     transport_security=TransportSecuritySettings(
                                         enable_dns_rebinding_protection=True,
                                         allowed_hosts=["127.0.0.1", "127.0.0.1:*"],
                                         allowed_origins=["https://claude.ai"]))
    return SecretPathGate(app, secret), uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["init", "serve"])
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--backend", choices=["rules", "laya"], default="rules")
    parser.add_argument("--checkpoint", type=Path)
    args = parser.parse_args()
    if os.name != "nt" or not 1024 <= args.port <= 65535:
        raise ValueError("Windows and a non-privileged TCP port are required")
    bundle = args.bundle.resolve(strict=True)
    directory = args.directory.resolve()
    secret = read_or_create_secret(directory)
    if args.mode == "init":
        print(json.dumps({"status": "initialized", "directory": str(directory),
                          "secret_length": len(secret), "secret_not_printed": True}))
        return
    app, uvicorn = create_app(bundle, directory, secret, args.backend,
                              args.checkpoint.resolve(strict=True) if args.checkpoint else None)
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning", access_log=False)


if __name__ == "__main__":
    main()
