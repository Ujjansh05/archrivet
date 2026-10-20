# ArchRivet desktop preview

Development checkout note: the live viewer requires rebuilding the engine wheel and desktop bundle together. The checked-in older vendor wheel and published v0.3.0a2 installers do not contain the new viewer. See [the preview guide](../../docs/live-diagram.md) for a working source-based walkthrough.

Choose **Rules** for the smallest installation: no Torch, Laya, model weights or GPU. The separate **Laya CPU** variant includes model dependencies and an optional experimental 322M model. Both use the same engine and review tools. This source version also adds five tools for an optional live architecture diagram; published packages gain them when a new release is built.

| Variant | Package | Dependencies |
|---|---|---|
| Rules | `archrivet-windows-x64-rules-0.3.0-alpha.1.mcpb` or `.zip` | Python and core MCP/review libraries. |
| Laya CPU | `archrivet-windows-x64-laya-cpu-0.3.0-alpha.1.mcpb` or `.zip` | Core libraries and CPU model runtime. Weights download only after opt-in. |

Use the matching [GitHub release assets](https://github.com/Ujjansh05/archrivet/releases). A source checkout is not a built extension. Initial dependency setup requires internet. Actual desktop GUI testing remains pending; protocol tests do not establish GUI compatibility or directory approval.

## Install or replace

Windows x64 hosts supporting **MCPB 0.4 with the UV runtime** manage Python/dependencies from the MCPB. Codex users extract the selected ZIP into a new folder and register it with an installed `uv`:

```powershell
codex mcp add archrivet -- uv run --frozen --managed-python --directory "C:\Apps\ArchRivet-Rules" server/main.py
```

For Laya CPU, use its directory and explicitly opt in:

```powershell
codex mcp add archrivet --env ARCHRIVET_ENABLE_LAYA=true -- uv run --frozen --managed-python --directory "C:\Apps\ArchRivet-Laya" server/main.py
```

Compatible desktop hosts expose **Enable experimental local Laya model** only in the Laya CPU variant, disabled by default. The approximately 1 GB checkpoint expands to approximately 1.3 GB, in addition to runtime dependencies. The Rules bundle rejects a model-enable environment flag with an instruction to replace the bundle.

**Both variants use the identity `archrivet`: replace the existing registration, do not install both.** Close the old assistant session first. If the host cannot replace the same identity/version, remove its old registration and install the desired variant. For Codex, run `codex mcp remove archrivet` before the appropriate command above. Switching to Rules must remove the previous model opt-in. Use a new extraction folder so an old `.venv` cannot retain model libraries.

Preserve `%USERPROFILE%\.archrivet-extension` and any custom `ARCHRIVET_EXTENSION_HOME`/`ARCHRIVET_MODEL_DIR`. Existing verified model files are reused; the checkpoint ID/checksums are unchanged. Temporary review IDs do not migrate. Do not delete model data when replacing a registration.

## Actual readiness and recovery

Ask the assistant to call `get_setup_status`. It reports setup timings and download progress without reviewing an architecture:

- `not_requested`: Rules mode, no model enabled.
- `checking`, `downloading`, `verifying`, `extracting`: preparing model files.
- `files_ready`: verified files exist; inference is not ready yet.
- `loading_model`: importing libraries, checking the contract and loading weights.
- `ready`: the model worker has finished initialization.
- `unloaded`: idle memory release or worker exit; the next review starts initialization again.
- `failed`, `paused`, `waiting_for_other_install`: read the error and call `retry_model_setup` when appropriate.

`cancel_model_setup` pauses unfinished setup and preserves resumable files; `cancel_review` cancels a review. Cancellation is observed between bounded download/checksum/extraction operations and during worker initialization. Requested Laya never silently falls back to Rules when unavailable.

## Try a clarification

> Review my price cache. Prices must be under five seconds old. Normal responses are at most three seconds old. During an outage we serve saved prices, but their maximum age is unspecified. Name the missing detail and keep capacity unknown without a relevant load test.

Then add: **During outages, prices can be 60 seconds old. Rerun and compare.** The result should change from a missing detail to a conflict with the five-second requirement. Proposed fixes remain separate from implemented guarantees.

## Runtime boundaries

The extension uses session-local stdio. Reviews need no detached daemon. The optional diagram opens a private loopback listener only when requested. Each host session may load its own worker; cross-host model sharing is not provided. Reviews have bounded queues and cancellation; idle workers release memory. Closing a session ends its jobs and diagram listener, while model files stay reusable.

ArchRivet sends no architecture text to a remote inference service; your assistant's provider/storage settings still apply. It reviews supplied facts and estimates demand, not deployed code or tested production capacity. Laya is experimental; confidence is not production failure probability.

## Try the live diagram

> Design a small online store. Open an ArchRivet architecture diagram beside our conversation, and update that same diagram whenever we change the design. Show which components are proposed and which details are unknown.

Then ask: **Add a queue for sending order emails, and update the diagram.** The assistant calls `update_architecture_view` with the revised graph. You can close the browser tab and keep talking; updates do not reopen it. Ask to reopen the diagram when you want it again, or ask to close the view to deactivate it.

The viewer needs no model or GPU. It displays the assistant's supplied graph, so updates happen when the assistant calls the tool. The picture does not prove that an architecture is correct or has tested capacity. Keep the private viewer URL within your session.

This companion opens a browser on the computer running the MCP server. A local terminal or desktop assistant can use it if it supports these MCP tools. It is not an embedded panel in every host; a remote MCP server cannot open a window on your computer.

## Build both variants

```powershell
python -m build --wheel
python scripts/build_desktop_variants.py --wheel dist/architecture_review_plugin-0.3.0a2-py3-none-any.whl --output .runtime/desktop-variants
```

Use a new output directory. `--offline` uses cached dependency metadata. The builder locks both graphs, rejects model dependencies in Rules, and creates two MCPB/ZIP pairs plus `bundle-audit.json`. The same engine wheel is included in both. No model weights, private training data or development environment are packaged. GUI installation must still be tested independently.
