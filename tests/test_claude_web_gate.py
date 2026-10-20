"""The temporary public tunnel must expose only its secret MCP route."""

import httpx
import pytest

from scripts.claude_web_test_host import SecretPathGate, read_or_create_secret


@pytest.mark.asyncio
async def test_secret_path_gate_limits_route_host_and_origin():
    received = []

    async def inner(scope, _receive, send):
        received.append(scope["path"])
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    app = SecretPathGate(inner, "A" * 43)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                 base_url="http://127.0.0.1:8765") as client:
        assert (await client.post("/mcp")).status_code == 404
        assert (await client.post("/" + "A" * 43 + "/mcp")).status_code == 204
        assert (await client.post("/" + "A" * 43 + "/mcp", headers={
            "Host": "untrusted.example.com"})).status_code == 404
        assert (await client.post("/" + "A" * 43 + "/mcp", headers={
            "Origin": "https://untrusted.example.com"})).status_code == 404
        assert (await client.post("/" + "A" * 43 + "/mcp", headers={
            "Host": "random-name.trycloudflare.com"})).status_code == 204
    assert received == ["/mcp", "/mcp"]


def test_secret_is_reused_without_printing_or_shortening(tmp_path):
    first = read_or_create_secret(tmp_path)
    assert len(first) >= 40
    assert read_or_create_secret(tmp_path) == first
    assert (tmp_path / "secret.txt").read_text(encoding="ascii").strip() == first
