# OpenAI plugin upload candidate — 22 October 2026

This is a Windows x64 **local MCP** package for ArchRivet Rules mode. It bundles Python and its dependencies. It does not include or download Laya. It is a candidate for OpenAI's desktop-only plugin route, not an approved or published plugin.

## Artifact

- File: `archrivet-openai-windows-x64-0.4.0-alpha.2.zip`
- SHA-256: `02e28820f351c8bd27307176dc8dfc4e17851f1edf11d1b27319e11b54da7827`
- Size: 26,629,950 bytes
- Contents: root `plugin.json` and `mcp.json`, bundled Windows Python runtime, current engine wheel, 36 runtime dependencies, notices and assets

The first upload candidate contained plugin-level review cases. The portal rejected those with a server-count error, even though its ZIP declared only one server. OpenAI's current guide says to use the **Skills only** flow for approved local MCP packages and says Skills-only submissions do not require MCP review cases or a demo recording. The corrected candidate therefore omits the plugin-level cases. The five positive and three negative examples remain available in the earlier source history; they are not imported for this local route.

The upload copy is in `C:\Users\ujjan\archrivet-live-viewer\.runtime\archrivet-openai-windows-x64-0.4.0-alpha.2.zip`. The source build, dependency audit and extracted-package validation are under `.runtime/readme-motion-worktree/.runtime/openai-upload-20261022/` in the local checkout. These local paths are not part of the ZIP.

## Local checks

- The package builder verified installed dependency file hashes and produced 2,485 bundled files.
- Portable plugin and MCP JSON Schemas passed against the downloaded schema copies.
- The extracted ZIP launched its own Python runtime, exposed 14 annotated MCP tools, and passed local checks for missing facts, changed verdicts, deadline arithmetic, workload calculations, proposal preview, diagram updates, viewer access controls and error handling.
- Focused package, annotation and proposal tests: 54 passed, 1 skipped. Ruff passed for the changed validator.
- The exact copied ZIP matches the SHA-256 above.

The validation script was updated from 13 to 14 expected tools after `preview_proposal` was added. It now permits omitted review cases for the local Skills-only route. These checks exercise the package over stdio, not an actual ChatGPT desktop installation or the OpenAI submission portal.

## Before submitting for review

OpenAI's [desktop-only submission instructions](https://developers.openai.com/plugins/deploy/desktop-only) currently limit local MCP submissions to approved partners. The publisher must have the organization allowlisted, complete identity verification and test a clean ChatGPT desktop installation. Follow the [upload and submission guide](https://developers.openai.com/plugins/deploy/submission): upload this ZIP through the approved local-MCP route, inspect automated findings, and submit the draft for review. OpenAI's guide says Skills-only submissions do not need MCP review cases or a demo recording. Approval and publication are separate actions.

The manifest references public privacy, terms and support pages in the repository. Check that the portal can reach them and that the verified publisher identity matches the listing. The automated portal scan, account eligibility, real-host workflow and recording remain unverified by this local build. `protocol-validation.json` records `submission_ready: false` for that reason.
