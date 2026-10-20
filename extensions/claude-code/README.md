# ArchRivet for Claude Code — Windows preview

This plugin gives Claude Code an ArchRivet review skill and a local MCP server. It reviews explicitly supplied backend design facts, identifies missing information, calculates workload demand, and can open a separate local architecture diagram. The packaged preview uses the rules engine and includes no Laya model weights. It does not certify production capacity without matching benchmark evidence.

To test a built, extracted package in a Claude Code terminal session:

```powershell
claude --plugin-dir "C:\path\to\extracted\archrivet"
```

Try `/archrivet:review-architecture` or ask: “Review my backend design. Messages go into a queue; a worker writes a database row and acknowledges afterwards. What happens if it crashes before the ack? Then propose a safer flow and preview that proposal separately.” A useful response should name the missing idempotency detail, then show conditional findings for the proposed fix. The preview assumes its facts; it does not verify a deployment. For a diagram, ask Claude to open one and then revise it.

The MCP server works locally without an account, API key, GPU, or model download. Claude Code itself still requires its usual sign-in. The archive is for Windows x64 only. Unpack it before using `--plugin-dir`; the directory must contain `.claude-plugin/plugin.json`, `.mcp.json`, `launch.py`, and `runtime/python.exe`.

The plugin stores its public evidence cache under `%USERPROFILE%\.archrivet-claude-code`. Review text and diagrams remain in process memory until that MCP server exits; saved diagram exports persist where the user saves them. See `PRIVACY.md` and `TERMS.md`.
