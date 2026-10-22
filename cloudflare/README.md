# ArchRivet Laya gateway

This free Cloudflare Worker is an HTTPS front door for ArchRivet. It does not run rules or model inference. Every review is forwarded to the separately hosted fine-tuned Laya checkpoint. If that host is unavailable, the gateway returns 503 rather than substituting a rules-only answer.

1. Set up the Oracle Always Free A1 VM with [the deployment guide](../docs/public-laya-deployment.md). Confirm that its HTTPS hostname works and returns 401 on `/mcp` without a token.
2. From this directory, run `npm ci` and `npx wrangler login` if needed.
3. Run `npx wrangler secret put LAYA_ORIGIN_URL` and enter the VM's HTTPS origin, ending in `/`.
4. Run `npx wrangler secret put LAYA_ORIGIN_TOKEN` and enter only the value after `ARCH_REVIEW_HTTP_TOKEN=` in the VM's `/etc/archrivet/http.env`.
5. Run `npm test`, then `npx wrangler deploy`. The public MCP URL is `https://archrivet-mcp.<your-workers-subdomain>.workers.dev/mcp`.
6. Test MCP initialization, `get_review_schema`, and one `review_design`/`get_review` pair. Confirm `backend.name` is `laya`, `model_decision` is present, and `coverage.inference_errors` is empty. Do not advertise the endpoint until that passes.

For OpenAI's plugin submission, set the exact portal challenge with `npx wrangler secret put OPENAI_DOMAIN_CHALLENGE`, rescan, and follow the [official submission steps](https://developers.openai.com/plugins/deploy/submission). The Worker returns that token at `/.well-known/openai-apps-challenge`.

The Worker URL stays the same when the model host changes. The free VM can still be unavailable or reclaimed; the URL is not a guaranteed always-on service. Do not put the origin token or architecture documents in repository files or Wrangler variables committed to Git.
