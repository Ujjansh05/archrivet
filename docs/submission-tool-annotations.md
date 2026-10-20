# MCP tool annotations

The desktop server declares all four MCP safety hints explicitly. The shared
diagram tools use the same declarations in the desktop server and ordinary CLI
server. Hints describe behavior; they do not grant permission or bypass the host's
approvals.

The classifications follow OpenAI's [plugin guidelines](https://developers.openai.com/plugins/plugin-guidelines#correct-annotation)
and [tool planning guidance](https://developers.openai.com/plugins/plan/tools).
Stateful jobs are writes. Cancellation and replacement of existing data are
destructive effects, including reversible changes. Read operations and local
computations without such effects are read-only. Internet access is distinguished
from the bounded local viewer.

| Tool | Read only | Destructive | Idempotent | Open world | Reason |
|---|---|---|---|---|---|
| `get_setup_status` | true | false | true | false | Reads current mode and setup status; does not start setup. |
| `retry_model_setup` | Rules only | Laya only | Rules only | Laya only | May download a pinned public GitHub artifact, install files, replace an invalid partial download, and start a worker after explicit model opt-in. Retries can restart failed setup. Rules bundles return a no-op status. |
| `cancel_model_setup` | Rules only | Laya only | true | false | Cancels pending setup, preserving verified and partial files. Repeating cancellation requests has no further cancellation effect. Rules bundles have no setup job to cancel. |
| `get_review_schema` | true | false | true | false | Returns the supported checks and input contract. |
| `review_design` | false | Laya only | false | Laya only | Queues a new review and may build the local evidence index. An enabled, unloaded model can restart setup, replace invalid partial downloads, and download missing files. Every submitted review gets a new job. |
| `get_review` | true | false | true | false | Reads a session review; job expiration remains part of the cache lifecycle. |
| `cancel_review` | false | true | true | false | Requests cancellation; repeated cancellation has no additional effect. |
| `compare_reviews` | true | false | true | false | Computes a comparison of completed session reviews. |
| `create_architecture_view` | false | true | false | false | Creates a view and local listener, optionally opens a browser, and can evict a closed view when the eight-view limit is reached. |
| `update_architecture_view` | false | true | true | false | Replaces the graph. An identical retry with the same expected revision is rejected before any additional change; a new revision is a different input. |
| `get_architecture_view` | true | false | true | false | Reads the session's current graph and private viewer URL. |
| `open_architecture_view` | false | false | false | false | Activates an existing local view and opens its fixed loopback URL. Repeating may create another browser tab. No arbitrary destination can be supplied. |
| `close_architecture_view` | false | true | false | false | Deactivates a view. The timestamp changes on each call, so strict retry idempotency is not claimed. The graph is retained until session close or eviction. |

The Laya download classification is conservative across optional setup states;
an opted-out Laya bundle does not download. The submitted Rules build has both
download-capable hints set to `false`, matching that build's actual restriction.
Neither build uploads architecture text to the model-download service.

Focused tests check the complete desktop tool list, explicit booleans, shared
CLI diagram declarations, and behavior underlying non-read-only classifications.
These are protocol and implementation checks, not evidence of ChatGPT approval
or completed ChatGPT desktop installation testing.
