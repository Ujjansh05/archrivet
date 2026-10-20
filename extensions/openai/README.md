# ArchRivet for OpenAI desktop — submission candidate

This Windows x64 package reviews supplied backend design facts through MCP.
It includes Python and the rules engine; no commands, accounts or model downloads
are needed after installation by a compatible host. No OpenAI API key is required.
The assistant still needs to call the tools with the facts from your design.

Ask: **“Review my design and tell me what details are missing.”** Then answer the
follow-up questions and ask for a comparison. Ask to open a diagram to see a
separate local browser window. Updates happen when the assistant sends a revised
graph. Closing the diagram does not close the conversation.

Eight narrow checks cover retries, acknowledgements, queue overload,
transactions, replicas, cache freshness, failover and dependency deadlines.
Workload numbers are formulas using supplied assumptions. Throughput and latency
capacity need benchmark evidence. A diagram does not prove a design is correct.

This package is a **candidate for testing**, not an approved directory listing.
The experimental Laya checkpoints are not included. The optional Laya desktop
variant is a separate product artifact; this package cannot enable or download it.

OpenAI currently limits local MCP submissions to approved partner organizations.
After allowlisting, upload the built ZIP through the local MCP submission route
and complete identity verification, real desktop testing and review requirements.
Do not upload this source folder: use the self-contained ZIP built by
`scripts/build_openai_plugin.py` in the repository.

Public privacy and terms links in the manifest are planned destinations. Publish
and verify those pages and add a real host walkthrough recording before submitting.
The developer name must match the identity verified in the submission portal.

The plugin stores its packaged public evidence index and setup status under
`%USERPROFILE%\.archrivet-openai`. Review text/results and diagrams are in memory;
the host and browser have their own history policies. Close the host's MCP session
to release those in-memory objects. Once the host is stopped, this local folder
can be removed to delete the plugin's generated cache. Browser exports persist
where the user saves them. See PRIVACY.md and TERMS.md in this package.

Support: https://github.com/Ujjansh05/archrivet/issues
Requirements checked: https://developers.openai.com/plugins/deploy/desktop-only
