"""The public HTTP transport must refuse a rules-only configuration."""
import pytest

from arch_review.mcp_server import run_http


def test_http_mcp_requires_laya_checkpoint(tmp_path, monkeypatch):
    monkeypatch.setenv("ARCH_REVIEW_HOME", str(tmp_path))
    monkeypatch.setenv("ARCH_REVIEW_HTTP_TOKEN", "x" * 40)
    with pytest.raises(RuntimeError, match="configured Laya checkpoint"):
        run_http(18789)
