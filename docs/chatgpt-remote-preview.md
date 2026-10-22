# ChatGPT remote MCP preview

The public gateway is `https://archrivet-mcp.humour-hub-beta.workers.dev/mcp`. It is a Cloudflare Worker. It forwards requests to a separate Laya review service running on the maintainer's PC; Cloudflare does not run the model. The Worker URL is stable, but the current backend connection uses a temporary Cloudflare quick tunnel. The MCP is available only while the PC, review service and tunnel are running. This is suitable for a draft and live testing, not a durable public submission endpoint.

On the configured Windows PC, restart the preview from PowerShell:

```powershell
& "C:\Users\ujjan\architecture-review-plugin\.runtime\chatgpt-release\scripts\start_cloudflare_laya_preview.ps1"
```

The script starts the configured Laya service, warms up the token-protected local MCP, opens a quick tunnel with the correct Host header, updates the Worker's origin URL and token secrets, and checks the public MCP handshake. It requires the configured `H:\archrivet-gpu-runtime` Python environment, the merged checkpoint referenced by `.runtime\live\settings.json`, `cloudflared`, `npx`/Wrangler, Cloudflare sign-in, and an awake PC. Keep the local `.runtime\live\http-token.txt` private.

The ChatGPT draft package is built with:

```powershell
& "H:\archrivet-gpu-runtime\venv\Scripts\python.exe" "C:\Users\ujjan\architecture-review-plugin\.runtime\chatgpt-release\scripts\build_openai_remote_plugin.py"
```

Create a **new** plugin draft for this MCP package. OpenAI currently does not support adding an MCP server to the earlier skills-only ArchRivet draft. The new package name is `archrivet-mcp`, while its display name remains ArchRivet.

Upload `dist\archrivet-openai-remote-laya-0.4.0-alpha.3.zip` through **With MCP**. It contains one remote Streamable HTTP server and no weights, code runtime or secrets. The remote preview's [privacy notice](https://archrivet-mcp.humour-hub-beta.workers.dev/privacy) and [terms](https://archrivet-mcp.humour-hub-beta.workers.dev/terms) are public. If the portal asks for domain verification, enter its challenge value interactively with `npx wrangler secret put OPENAI_DOMAIN_CHALLENGE` from `cloudflare/`, then rescan. The Worker serves it at `/.well-known/openai-apps-challenge`.

Before **Submit for review**, move the Laya service to an always-on host and update the Worker's `LAYA_ORIGIN_URL` and `LAYA_ORIGIN_TOKEN` secrets. Keep the Worker URL in the ZIP unchanged. OpenAI's [remote MCP review requirements](https://developers.openai.com/plugins/deploy/app-review) say the server cannot be a local or testing endpoint. Also complete the five positive and three negative cases with a real ChatGPT host, provide a public video walkthrough, and resolve any portal findings. The model is an experimental specialist with unvalidated calibration; do not claim production accuracy or measured capacity.
