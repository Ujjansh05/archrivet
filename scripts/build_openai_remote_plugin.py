"""Build the small remote-MCP ChatGPT draft; never bundle model weights or secrets."""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path
from urllib.parse import urlsplit
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "extensions" / "openai-remote"
MEMBERS = ("plugin.json", "mcp.json", "assets/icon.png")


def build(output: Path) -> dict:
    plugin = json.loads((PACKAGE / "plugin.json").read_text(encoding="utf-8"))
    if plugin["name"] != "archrivet-mcp":
        raise ValueError("Use a new MCP package name; the previous ArchRivet draft was skills-only")
    mcp = json.loads((PACKAGE / "mcp.json").read_text(encoding="utf-8"))
    servers = mcp["mcpServers"]
    if set(servers) != {"archrivet"}:
        raise ValueError("Remote package must contain exactly one ArchRivet MCP server")
    server = servers["archrivet"]
    url = urlsplit(server["url"])
    if (server["type"] != "streamable-http" or url.scheme != "https" or not url.hostname
            or url.path != "/mcp" or url.query or url.fragment or url.username or url.password):
        raise ValueError("A public HTTPS Streamable HTTP MCP endpoint is required")
    if set(server) != {"type", "url"}:
        raise ValueError("The public preview must declare only its HTTPS endpoint; portal auth is none")
    interface = plugin["extensions"]["com.openai"]["interface"]
    for field in ("websiteURL", "supportURL", "privacyPolicyURL", "termsOfServiceURL"):
        if urlsplit(interface[field]).scheme != "https":
            raise ValueError(f"{field} must be a public HTTPS URL")
    cases = plugin["extensions"]["com.openai"]["review"]["test_cases"]
    if len(cases["positive"]) != 5 or len(cases["negative"]) != 3:
        raise ValueError("Expected five positive and three negative review cases")
    icon = (PACKAGE / "assets" / "icon.png").read_bytes()
    if icon[:8] != b"\x89PNG\r\n\x1a\n" or struct.unpack(">II", icon[16:24]) != (128, 128):
        raise ValueError("Expected the 128-pixel ArchRivet PNG icon")
    if any(key in server for key in ("env", "headers", "token", "apiKey")):
        raise ValueError("Do not include origin credentials in the package")

    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for name in MEMBERS:
            archive.write(PACKAGE / name, name)
    with ZipFile(output) as archive:
        if tuple(archive.namelist()) != MEMBERS or archive.testzip() is not None:
            raise ValueError("ZIP inventory or integrity check failed")
    return {"zip": str(output.resolve()), "bytes": output.stat().st_size,
            "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            "endpoint": server["url"], "members": list(MEMBERS),
            "portal_upload_tested": False, "review_submitted": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        default=ROOT / "dist" / "archrivet-openai-remote-laya-0.4.0-alpha.3.zip")
    args = parser.parse_args()
    print(json.dumps(build(args.output), indent=2))
