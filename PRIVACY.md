# ArchRivet privacy notice

Updated 20 October 2026. This notice covers the self-contained Windows x64 Rules package prepared for local MCP hosts, including Claude Code. The Rules package contains no Laya runtime or model download; separate Laya-capable distributions are distinguished below.

ArchRivet is maintained by [Ujjansh05](https://github.com/Ujjansh05). This notice covers ArchRivet's local review tools and browser diagram viewer. It does not cover the AI application you connect to ArchRivet, GitHub, or a modified distribution.

## Information used

Your AI application sends ArchRivet the architecture text, structured design facts, requirements, workload assumptions, and diagram data needed for the requested task. ArchRivet uses that information to produce scoped findings, clarification questions, calculations, and diagrams. It returns results to the same application over MCP.

The standard desktop package does not require an ArchRivet account. It does not include advertising, analytics, or a service that uploads your architecture to the maintainer. The local tools do not use submitted designs to train a model. Your AI application can independently send or retain the conversation and tool results under its own settings and privacy policy; using a local plugin does not make that entire conversation local.

## Local storage and retention

- Review jobs and their results are held in the local process's memory. Finished jobs normally expire after one hour; older finished jobs may be removed sooner when the bounded job store fills. Ending the MCP process clears its in-memory jobs.
- Diagram state is held in memory for the MCP session. Closing its browser tab or deactivating a view does not erase the graph immediately. Ending the MCP process clears it. You can save JSON or SVG exports yourself; those files remain where your browser saves them until you delete them.
- The OpenAI Rules package creates its local evidence search index and lock files under `.archrivet-openai` in your user home. Separate desktop distributions normally use `.archrivet-extension` and can also store optional downloaded model files there. The evidence index contains the bundled reference lessons, not a stored copy of your submitted architecture.
- Your browser may retain the local viewer URL in history. That URL contains a temporary access token. Keep it private. Browser history, exports, operating-system logs or crash dumps, and host conversation history have their own retention settings.

After closing the MCP process, you can remove ArchRivet's local data directory and any exports you saved. Uninstalling a host plugin may leave its local caches. Remove host conversation history or browser history through those applications separately. The maintainer cannot remotely read or erase files on your computer.

## Network activity

The viewer serves packaged assets from `127.0.0.1` and does not load remote scripts or fonts. It uses a per-view token for diagram requests. It opens a separate browser window or tab only through the requested viewer workflow.

The Rules package does not download model weights. In a separate Laya-capable distribution, explicitly enabling Laya can download the pinned model archive from GitHub and its delivery infrastructure. Download services receive ordinary connection information such as your IP address and request details; the model download does not include your architecture. Model inference then runs locally. Other installation methods may contact package registries to obtain software dependencies. Opening source references, project links, or support pages sends a request to the selected website.

## Support and changes

You can contact the maintainer through [GitHub Issues](https://github.com/Ujjansh05/archrivet/issues). Issues are public: describe the problem with a small invented example, and do not include passwords, tokens, private viewer URLs, or confidential architecture. Information you post there is handled by GitHub and is visible to the project maintainers and other visitors.

Changes to ArchRivet's data handling will be described in this notice and the release notes. Review the notice shipped with the version you install.
