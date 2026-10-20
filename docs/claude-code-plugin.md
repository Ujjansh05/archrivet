# Claude Code plugin preview

This is a **local Windows x64 preview**, not yet a GitHub release or Anthropic directory listing. It bundles ArchRivet's rules engine and Python runtime. The separate experimental Laya checkpoint is not included. Its `preview_proposal` tool checks proposed changes conditionally; it does not verify a deployment.

## Build and verify locally

Starting from an audited OpenAI rules bundle made by `scripts/build_openai_plugin.py`:

```powershell
python scripts/build_claude_plugin.py --source-bundle ".runtime\openai-submission-candidate\bundle" --output ".runtime\claude-code-candidate"
claude plugin validate ".runtime\claude-code-candidate\archrivet"
claude --plugin-dir ".runtime\claude-code-candidate\archrivet"
```

The builder verifies the source inventory before copying, writes a separate archive, and includes no private training files. The Claude MCP command points to the packaged `runtime/python.exe` and `launch.py`. Sign in with `claude auth login` if Claude Code reports that you are logged out. In the session, run `/archrivet:review-architecture` or use the [order-flow prompt](claude-launch.md). Use `/mcp` to inspect the `archrivet` connection. The local package and protocol checks do not prove that Claude selects tools correctly in a real conversation; a real Claude Code host test is still pending.

## Early-access publication

Upload the ZIP produced by `scripts/build_claude_plugin.py` as a versioned GitHub Release asset. Users can download, extract, and use `claude --plugin-dir <extracted-archrivet-directory>`. The repository now contains `.claude-plugin/marketplace.json`, which pins the archive and needs Claude Code 2.1.224 or newer. A live Claude Code conversation test is still pending account sign-in; label this release early access and collect reports of host behavior. Validate the marketplace with a compatible CLI when available. The entry uses this form:

```json
{
  "name": "archrivet-marketplace",
  "description": "ArchRivet releases for Claude Code",
  "owner": {"name": "Ujjansh05"},
  "plugins": [{
    "name": "archrivet",
    "source": {
      "source": "archive",
      "url": "https://github.com/Ujjansh05/archrivet/releases/download/v0.4.0a1/archrivet-claude-code-windows-x64-0.4.0-alpha.1.zip",
      "sha256": "fa7fc1e845fc14bc3373685e20d43bf7b682b3969238d76139c47bb314a6b175"
    }
  }]
}
```

Users can then run `claude plugin marketplace add Ujjansh05/archrivet` and `claude plugin install archrivet@archrivet-marketplace`. Do not advertise an untested host run or a Laya-backed plugin for this rules-only package.

Claude Code documentation: [plugins](https://code.claude.com/docs/en/plugins), [plugin manifest](https://code.claude.com/docs/en/plugins-reference), [marketplaces](https://code.claude.com/docs/en/plugin-marketplaces).
