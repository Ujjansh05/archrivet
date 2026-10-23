import assert from "node:assert/strict";
import test from "node:test";
import gateway from "../src/index.js";

const env = { LAYA_ORIGIN_URL: "https://model.example.com/", LAYA_ORIGIN_TOKEN: "test-secret-token" };

test("refuses an unconfigured model origin", async () => {
  const response = await gateway.fetch(new Request("https://archrivet.example/mcp", { method: "POST", body: "{}" }), {});
  assert.equal(response.status, 503);
});

test("forwards MCP to the Laya host while replacing caller credentials", async () => {
  const previous = globalThis.fetch;
  let forwarded;
  globalThis.fetch = async (url, options) => {
    forwarded = { url: String(url), ...options };
    return new Response(JSON.stringify({ jsonrpc: "2.0", id: 1, result: { tools: [] } }),
      { headers: { "content-type": "application/json" } });
  };
  try {
    const response = await gateway.fetch(new Request("https://archrivet.example/mcp", {
      method: "POST", headers: { authorization: "Bearer attacker-token", "content-type": "application/json",
        "mcp-protocol-version": "2025-06-18" }, body: "{}"
    }), env);
    assert.equal(response.status, 200);
    assert.equal(forwarded.url, "https://model.example.com/mcp");
    assert.equal(forwarded.headers.get("authorization"), "Bearer test-secret-token");
    assert.equal(forwarded.headers.get("mcp-protocol-version"), "2025-06-18");
    assert.equal(response.headers.get("cache-control"), "no-store");
  } finally {
    globalThis.fetch = previous;
  }
});

test("forwards modern MCP discovery and tool routing headers", async () => {
  const previous = globalThis.fetch;
  let forwarded;
  globalThis.fetch = async (_url, options) => {
    forwarded = options.headers;
    return Response.json({ jsonrpc: "2.0", id: 1, result: { supportedVersions: ["2026-07-28"] } });
  };
  try {
    const response = await gateway.fetch(new Request("https://archrivet.example/mcp", {
      method: "POST",
      headers: {
        "content-type": "application/json", "mcp-protocol-version": "2026-07-28",
        "mcp-method": "server/discover", "mcp-name": "example",
        "mcp-param-check": "retry_safety", authorization: "Bearer caller-token"
      },
      body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "server/discover" })
    }), env);
    assert.equal(response.status, 200);
    assert.equal(forwarded.get("mcp-method"), "server/discover");
    assert.equal(forwarded.get("mcp-name"), "example");
    assert.equal(forwarded.get("mcp-param-check"), "retry_safety");
    assert.equal(forwarded.get("authorization"), "Bearer test-secret-token");
  } finally {
    globalThis.fetch = previous;
  }
});

test("does not accept an unencrypted model origin", async () => {
  const response = await gateway.fetch(new Request("https://archrivet.example/mcp", { method: "POST", body: "{}" }),
    { ...env, LAYA_ORIGIN_URL: "http://model.example.com/" });
  assert.equal(response.status, 503);
});

test("serves the exact OpenAI domain challenge", async () => {
  const response = await gateway.fetch(new Request("https://archrivet.example/.well-known/openai-apps-challenge"),
    { ...env, OPENAI_DOMAIN_CHALLENGE: "verification-text" });
  assert.equal(await response.text(), "verification-text");
});

test("publishes remote-service privacy and terms pages", async () => {
  for (const path of ["privacy", "terms"]) {
    const response = await gateway.fetch(new Request(`https://archrivet.example/${path}`), {});
    assert.equal(response.status, 200);
    assert.match(response.headers.get("content-type"), /text\/html/);
    assert.match(await response.text(), /Laya|architecture/);
  }
});

test("returns 429 before forwarding when the preview rate limit is reached", async () => {
  const response = await gateway.fetch(new Request("https://archrivet.example/mcp", {
    method: "POST", body: "{}"
  }), { ...env, MCP_RATE_LIMITER: { limit: async () => ({ success: false }) } });
  assert.equal(response.status, 429);
  assert.equal(response.headers.get("retry-after"), "60");
});
