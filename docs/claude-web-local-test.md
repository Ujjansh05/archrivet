# Test ArchRivet in Claude web chat from this Windows PC

This is a private, temporary test of the **rules-only** ArchRivet review server. It exposes five MCP tools over Streamable HTTP with JSON responses: `get_review_schema`, `review_design`, `preview_proposal`, `get_review`, and `compare_reviews`. Proposal findings are conditional on supplied assumptions. The server does not expose file access, model setup, training, diagrams, or Laya weights. The URL contains a random bearer secret; anyone who gets the full URL can call these tools, so do not publish it.

From the repository directory, run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\manage_claude_web_test.ps1" -Action Start
Get-Content -LiteralPath ".runtime\claude-web-test\connector-url.txt"
```

The second command prints the private HTTPS MCP URL on **your own terminal**. Copy the complete URL, including the `/mcp` suffix. In Claude, go to **Customize → Connectors → Add custom connector**, name it `ArchRivet local test`, paste the URL, choose **No sign in** if asked, and add it. In the chat composer, use **+ → Connectors** to enable that connector. A plugin appearing under **Yours** is separate from this remote connection.

Test prompt:

> Use the ArchRivet connector. First call `get_review_schema`, then review this queue-to-database design: a worker writes an order and acknowledges the message afterward; the queue can redeliver after a crash. I need each order stored once, but I have not specified idempotency or what happens when the queue fills. Name each missing detail; do not invent capacity.

To check or stop the background processes:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\manage_claude_web_test.ps1" -Action Status
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\manage_claude_web_test.ps1" -Action Stop
```

The PC must remain awake, online, and running both background processes. Cloudflare Quick Tunnels are for testing, have no uptime guarantee, and assign a new hostname on restart. After a restart, run `Start` again and update the Claude connector URL; Claude may require removing and re-adding the connector to change its URL. The review engine performs workload arithmetic but does not certify production capacity. No GPU is used for this rules-only test.

This setup requires the previously extracted Windows plugin bundle at `.runtime/claude-code-extracted/archrivet` and an installed `cloudflared.exe`. The tunnel forwards only to `127.0.0.1:8765`. The secret and process state are stored in ignored `.runtime/claude-web-test/` files. Stop the tunnel when finished.

References: [Claude remote connector setup](https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp), [Cloudflare Quick Tunnels](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/).
