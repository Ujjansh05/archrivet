// The Worker is only an HTTPS gateway. Every architecture decision runs on the
// separately hosted, fine-tuned Laya checkpoint.
const FORWARDED_HEADERS = [
  "accept", "content-type", "mcp-protocol-version", "mcp-session-id", "last-event-id"
];
const RESPONSE_HEADERS = [
  "content-type", "mcp-session-id", "retry-after", "www-authenticate"
];

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
    if (incoming.pathname === "/.well-known/openai-apps-challenge" && request.method === "GET") {
      return env.OPENAI_DOMAIN_CHALLENGE
        ? new Response(env.OPENAI_DOMAIN_CHALLENGE, { headers: { "content-type": "text/plain", "cache-control": "no-store" } })
        : new Response("Not found", { status: 404 });
    }
    if (incoming.pathname === "/health" && request.method === "GET") {
      return Response.json({ service: "ArchRivet Laya MCP gateway", gateway_ready: Boolean(gatewayConfig(env)),
        model_health: "not_checked", model_host: "external_oracle_vm" },
      { headers: { "cache-control": "no-store" } });
    }
    if (incoming.pathname !== "/mcp" || !["POST", "GET", "DELETE"].includes(request.method)) {
      return new Response("Not found", { status: 404 });
    }
    const origin = gatewayConfig(env);
    if (!origin) return new Response("Laya origin is not configured", { status: 503 });
    const target = new URL("/mcp", origin);
    target.search = incoming.search;
    const headers = new Headers();
    for (const name of FORWARDED_HEADERS) {
      const value = request.headers.get(name);
      if (value !== null) headers.set(name, value);
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
