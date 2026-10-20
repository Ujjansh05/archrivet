---
name: review-architecture
description: Review a proposed backend architecture with ArchRivet's local MCP checks, workload calculations, missing-detail questions, and optional diagram.
---

Review the user's proposed architecture and its stated requirements. First call ArchRivet's `get_review_schema` to see the supported checks and accepted fields. Translate only facts actually supplied by the user or present in the design into a `review_design` request; mark their origins accurately. Do not invent queue guarantees, transaction boundaries, benchmarks, or traffic assumptions. Poll `get_review` until the review is complete.

Explain each verdict in plain language. For `insufficient_information`, name the exact missing detail and ask the relevant question. Show workload formulas and input assumptions; distinguish calculated demand from tested capacity. A `supported` result means the supplied facts satisfy that narrow check, not that a production deployment is proven safe.

When the user clarifies an existing design, rerun the relevant check and use `compare_reviews` to show what changed. When you invent an improved design, call `preview_proposal` instead. Its conditional verdict assumes the proposed facts are true; never label your own ideas `user_declared` or present a supported preview as a verified deployment. Keep the original review and the proposed preview separate, and name the tests that would confirm the proposal.

Use ArchRivet's diagram tools when the user asks to see or update a diagram. Tell the user when the diagram is a proposed design rather than an observed deployment.
