# OpenAI plugin upload candidate — 22 October 2026

This is a Windows x64 **local MCP** package for ArchRivet Rules mode. It bundles Python and its dependencies. It does not include or download Laya. It is a candidate for OpenAI's desktop-only plugin route, not an approved or published plugin.

## Artifact

- File: `archrivet-openai-windows-x64-0.4.0-alpha.1.zip`
- SHA-256: `1e34ac78335ccc85ff601bfeaf38d49a3c97ccb2f50069756f883b0620c7c16b`
- Size: 26,631,429 bytes
- Contents: root `plugin.json` and `mcp.json`, bundled Windows Python runtime, current engine wheel, 36 runtime dependencies, notices and assets

The upload copy is in `C:\Users\ujjan\archrivet-live-viewer\.runtime\archrivet-openai-windows-x64-0.4.0-alpha.1.zip`. The source build, dependency audit and extracted-package validation are under `.runtime/readme-motion-worktree/.runtime/openai-upload-20261022/` in the local checkout. These local paths are not part of the ZIP.

## Local checks

- The package builder verified installed dependency file hashes and produced 2,485 bundled files.
- Portable plugin and MCP JSON Schemas passed against the downloaded schema copies.
- The extracted ZIP launched its own Python runtime, exposed 14 annotated MCP tools, and passed local checks for missing facts, changed verdicts, deadline arithmetic, workload calculations, proposal preview, diagram updates, viewer access controls and error handling.
- Focused package, annotation and proposal tests: 54 passed, 1 skipped. Ruff passed for the changed validator.
- The exact copied ZIP matches the SHA-256 above.

The validation script was updated from 13 to 14 expected tools after `preview_proposal` was added. These checks exercise the package over stdio, not an actual ChatGPT desktop installation or the OpenAI submission portal.

## Before submitting for review

OpenAI's [desktop-only submission instructions](https://developers.openai.com/plugins/deploy/desktop-only) currently limit local MCP submissions to approved partners. The publisher must have the organization allowlisted, complete identity verification and test a clean ChatGPT desktop installation. Follow the [upload and submission guide](https://developers.openai.com/plugins/deploy/submission): upload this ZIP through the approved local-MCP route, inspect automated findings, provide the prepared five positive and three negative cases plus an accessible real-host recording, then submit the draft for review. Approval and publication are separate actions.

The manifest references public privacy, terms and support pages in the repository. Check that the portal can reach them and that the verified publisher identity matches the listing. The automated portal scan, account eligibility, real-host workflow and recording remain unverified by this local build. `protocol-validation.json` records `submission_ready: false` for that reason.
