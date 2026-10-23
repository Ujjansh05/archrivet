// The Worker is only an HTTPS gateway. Every architecture decision runs on the
// separately hosted, fine-tuned Laya checkpoint.
const FORWARDED_HEADERS = [
  "accept", "content-type", "mcp-protocol-version", "mcp-method", "mcp-name",
  "mcp-session-id", "last-event-id"
];
const RESPONSE_HEADERS = [
  "content-type", "mcp-session-id", "retry-after", "www-authenticate"
];

const LEGAL_PAGES = {
  "/privacy": {
    title: "ArchRivet privacy notice",
    body: `Updated 23 October 2026. This notice covers the public ArchRivet MCP preview.

When you ask an AI assistant to use ArchRivet, it sends the architecture text, requirements, structured facts and workload assumptions needed for the review to this HTTPS gateway. Cloudflare forwards the request through an encrypted tunnel to a Laya-backed review service operated by the project maintainer. The service returns scoped findings to the assistant. Do not submit confidential designs or secrets to this public preview.

Review jobs and results are held in the review service's memory and normally expire within one hour; they may be removed sooner when the job store fills. ArchRivet does not use submitted designs to train Laya and does not intentionally save design inputs in persistent application logs. Cloudflare and your AI provider may process network and conversation data under their own policies. The service does not require an ArchRivet account or use advertising analytics.

For support, open an issue at https://github.com/Ujjansh05/archrivet/issues using an invented example. GitHub issues are public. The preview runs on maintainer-operated hardware and may be unavailable without notice.`
  },
  "/terms": {
    title: "ArchRivet terms of use",
    body: `Updated 23 October 2026. ArchRivet is an experimental, free public preview maintained by Ujjansh05. It reviews supplied facts for scoped backend architecture checks and uses a fine-tuned Laya model as an experimental specialist. Findings can be wrong. A supported verdict is not a production guarantee, a security audit, or a capacity benchmark.

The service does not deploy infrastructure, modify your systems or make purchases. You decide whether to act on a finding and must test your own design. Submit only information you are allowed to share with the project and your AI provider. The preview has no uptime or support commitment and may stop when maintainer-operated hardware is offline.

Project source is available under the MIT License at https://github.com/Ujjansh05/archrivet. Third-party model and dependency licenses remain their own. For questions, see https://github.com/Ujjansh05/archrivet/issues.`
  }
};

function legalPage(page) {
  const escape = value => value.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
  const paragraphs = page.body.split("\n\n").map(value => `<p>${escape(value)}</p>`).join("\n");
  return new Response(`<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${page.title}</title><main><h1>${page.title}</h1>${paragraphs}</main>`,
    { headers: { "content-type": "text/html; charset=utf-8", "cache-control": "public, max-age=3600", "x-content-type-options": "nosniff" } });
}

function gatewayConfig(env) {
  if (!env.LAYA_ORIGIN_URL || !env.LAYA_ORIGIN_TOKEN) return null;
  let url;
  try {
    url = new URL(env.LAYA_ORIGIN_URL);
  } catch {
    return null;
  }
  if (url.protocol !== "https:" || url.username || url.password || url.search || url.hash || url.pathname !== "/") {
    return null;
  }
  return url;
}

export default {
  async fetch(request, env) {
    const incoming = new URL(request.url);
    if (request.method === "GET" && LEGAL_PAGES[incoming.pathname]) {
      return legalPage(LEGAL_PAGES[incoming.pathname]);
    }
    if (incoming.pathname === "/.well-known/openai-apps-challenge" && request.method === "GET") {
      return env.OPENAI_DOMAIN_CHALLENGE
        ? new Response(env.OPENAI_DOMAIN_CHALLENGE, { headers: { "content-type": "text/plain", "cache-control": "no-store" } })
        : new Response("Not found", { status: 404 });
    }
    if (incoming.pathname === "/health" && request.method === "GET") {
      return Response.json({ service: "ArchRivet Laya MCP gateway", gateway_ready: Boolean(gatewayConfig(env)),
        model_health: "not_checked", model_host: "external" },
      { headers: { "cache-control": "no-store" } });
    }
    if (incoming.pathname !== "/mcp" || !["POST", "GET", "DELETE"].includes(request.method)) {
      return new Response("Not found", { status: 404 });
    }
    const origin = gatewayConfig(env);
    if (!origin) return new Response("Laya origin is not configured", { status: 503 });
    if (env.MCP_RATE_LIMITER) {
      const { success } = await env.MCP_RATE_LIMITER.limit({ key: "public-mcp" });
      if (!success) return new Response("ArchRivet is busy; retry later", {
        status: 429, headers: { "retry-after": "60", "cache-control": "no-store" }
      });
    }
    const target = new URL("/mcp", origin);
    target.search = incoming.search;
    const headers = new Headers();
    for (const name of FORWARDED_HEADERS) {
      const value = request.headers.get(name);
      if (value !== null) headers.set(name, value);
    }
    for (const [name, value] of request.headers) {
      if (name.startsWith("mcp-param-")) headers.set(name, value);
    }
    headers.set("authorization", `Bearer ${env.LAYA_ORIGIN_TOKEN}`);
    try {
      const response = await fetch(target, {
        method: request.method, headers,
        body: request.method === "POST" ? request.body : undefined,
        redirect: "manual"
      });
      const outgoing = new Headers({ "cache-control": "no-store" });
      for (const name of RESPONSE_HEADERS) {
        const value = response.headers.get(name);
        if (value !== null) outgoing.set(name, value);
      }
      return new Response(response.body, { status: response.status, headers: outgoing });
    } catch {
      return new Response("Laya origin is unavailable", { status: 503, headers: { "cache-control": "no-store" } });
    }
  }
};
