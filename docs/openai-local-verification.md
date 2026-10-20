# OpenAI candidate: local verification

Checked 17 October 2026. **Prepared and locally tested; not submitted, published,
or approved.** The user has not confirmed approved-partner access for local MCP.

Artifact: `archrivet-openai-windows-x64-0.4.0-alpha.1.zip`

SHA-256: `97d1625120880a32b4be61b2678824647ccbdec1ba60f03f582cb0f919b84f1b`

The Windows x64 ZIP is 26,715,421 bytes. It includes Python 3.12.13, 36 dependency
distributions, the Rules engine, the diagram viewer, and dependency notices. Its
2,484 extracted files match the build inventory. No model libraries or weights
are included. The exact engine wheel hash is recorded in the build audit.

| Check | Result |
|---|---|
| Complete Python test suite | 362 passed, 100.09 seconds |
| Ruff | Passed |
| Published portable plugin/MCP JSON schemas | Passed; OpenAI portal checks remain separate |
| Fresh extraction to a path containing spaces | Passed |
| Declared bundled stdio launch, PATH without development tools | Passed |
| All 13 desktop tools and effect annotations | Passed |
| Unknown cache facts → clarification → supported finding | Passed using explicitly supplied synthetic facts |
| 1,350 ms retry path without deadline propagation versus 1,000 ms requirement | Contradicted as expected |
| Peak demand 300/s, fan-out 600/s, retained storage 25.92 decimal GB | Correct arithmetic; capacity remains unknown |
| Diagram creation, connection updates, reading and closure | Passed over MCP; stale revisions rejected with recovery steps |
| Viewer authorization and origin checks | Missing token and foreign origin rejected; token absent from response body |
| Invalid checks, foreign job IDs, instructions inside source text | Rejected or treated as data as appropriate |
| Inherited Laya enable setting | Ignored by this Rules package; no model download |

The test client directly exercised MCP. It did not evaluate an assistant's choice
of tools, interpretation of prose, refusal of unrelated requests, or the actual
ChatGPT installation UI. The five positive and three negative review cases are
prepared; full host executions and the reviewer video are still required. Diagram
browser launching in the host was not claimed by the protocol test.

The runtime notices include observed version evidence and clearly marked inferred
dependency versions. The installed runtime was not independently compared to the
upstream release archive checksum. This inventory is not legal certification.

Local build outputs are in `.runtime/openai-submission-candidate`: the ZIP,
`SHA256SUMS.txt`, `build-audit.json`, `protocol-validation.json`, and `readiness.json`.
The builder's audit describes build-time checks; the separate protocol and
readiness reports record the subsequent extracted-package verification.

Remaining work: organization allowlisting, verified publisher, published and
verified HTTPS policy pages, a clean real desktop installation and all host review
cases, an accessible recording, and OpenAI's portal checks and attestations.
Follow the [submission checklist](openai-submission.md). No training, model
promotion, GitHub push, or external submission was performed in this preparation.
