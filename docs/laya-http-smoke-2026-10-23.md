# Laya HTTP MCP smoke test — 2026-10-23

Local test only; the Oracle host and public Worker are not deployed yet.

The server used the released `archrivet-322m-experimental-v0.2.0-alpha.1` merged checkpoint on CPU. Startup verified the checkpoint contract and waited for one Laya model decision before accepting MCP requests. An unauthenticated `/mcp` request returned 401; an authenticated MCP initialization returned the `architecture-review` server. A scoped `review_design`/`get_review` pair completed with `backend.name: laya`, a non-null `model_decision`, and no inference errors.

In the test design, the queue policy was explicitly `unbounded` while a fixed bound was required. The deterministic rule returned `contradicted`; Laya returned `insufficient_information` (probability 0.5885). The final result retained the rule contradiction and exposed `conflict: true`. This demonstrates model execution and honest disagreement handling, not improved accuracy.

Verification: five existing MCP/backend integration tests and the new rules-only refusal test passed. Four Cloudflare gateway tests passed. Wrangler's dry run bundled the gateway at 2.83 KiB (1.11 KiB gzip). The Oracle ARM64 deployment and an end-to-end public ChatGPT/Claude call remain untested.
