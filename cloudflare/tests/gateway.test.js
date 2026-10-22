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
