# Claude launch: practical early access

ArchRivet's first public use case is a scoped review of backend design flows. The assistant drafts and explains a system; ArchRivet checks explicit facts about retries, acknowledgement durability, queue overload, and five other defined risks. If the assistant proposes a revision, `preview_proposal` reports what that proposal would satisfy **if its assumed facts are true**. It does not certify a running system. Workload calculations are demand estimates; capacity stays unknown without a matching benchmark.

## Route 1: Claude Code plugin from GitHub

This is the quickest public path for a solo builder. Release the tested Windows x64 rules-only ZIP, then let early users download and extract it. A user starts Claude Code with:

```powershell
claude --plugin-dir "C:\path\to\extracted\archrivet"
```

In Claude Code, ask:

> Use ArchRivet to review this order flow. A request enters a queue; a worker writes the order, then acknowledges the message. The queue may redeliver after a crash. Tell me what detail is missing to know whether duplicates are prevented. Propose a safer design and use `preview_proposal` for the proposed design. Keep assumptions and production verification separate.

The rules package runs locally and requires no ArchRivet account, GPU, model download, or always-on server. It is a Claude Code plugin, **not** a Claude web-chat connector. After the first tested release, a public marketplace manifest can point to its versioned archive so users can run `claude plugin marketplace add Ujjansh05/archrivet` and `claude plugin install archrivet@archrivet-marketplace`. See [packaging instructions](claude-code-plugin.md).

## Route 2: Anthropic directory listing

Anthropic currently accepts directory submissions from Pro, Max, Team, and Enterprise plans; a free Claude account cannot submit. A public plugin repository can be submitted at [Claude's directory manager](https://claude.ai/directory/manage). Submission starts a review; it is not instant publication or an automatic endorsement. Test the packaged plugin in Claude Code first, document setup, privacy, and support, and submit its public repository after release. [Anthropic's directory guide](https://claude.com/docs/directory/publish) explains the current process.

## Claude web chat needs a different deployment

The private Cloudflare tunnel in this repository is for local connector tests while your PC is on. Its URL changes, the PC can go offline, and it has no public multi-user account isolation or production operating controls. Do not post its URL as a public service. To offer ArchRivet as a public Claude web connector, host a stable HTTPS MCP endpoint, add per-user access controls, rate limits, privacy and support documentation, and test every tool through the connector flow. Then submit the remote connector for Anthropic review. See [connector requirements](https://claude.com/docs/connectors/building/submission) and [review criteria](https://claude.com/docs/connectors/building/review-criteria).

## Feedback without a developer panel

An early-access release is reasonable if its scope is honest. Run the automated checks and one real Claude Code host test, then invite users to report redacted examples. Ask for the design text, the expected answer, the actual answer, which fact was missing or wrong, and the plugin version. Do not ask users to upload private architecture diagrams, API keys, or production logs. Fix reproducible mistakes first, keep the rules path as the default, and evaluate Laya separately before presenting it as an accuracy upgrade.
