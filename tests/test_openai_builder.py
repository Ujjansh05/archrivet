"""Package boundaries and dependency integrity, without copying a real interpreter."""
from __future__ import annotations

import base64
import csv
import hashlib
import importlib.util
import io
import zipfile
from email.message import Message
from importlib import metadata
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "openai_builder", Path(__file__).resolve().parents[1] / "scripts/build_openai_plugin.py")
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


@pytest.mark.parametrize("name", ["../secret", "/root/file", "C:/secret", "a\\b", "a//b", "a/./b",
                                 "name ", "folder./file", "CON.txt", "LPT1", "a:stream", "a|b", "a\x00b"])
def test_rejects_unsafe_windows_zip_paths(name):
    with pytest.raises(ValueError):
        builder.safe_member(name)


def test_dependency_entrypoints_are_omitted_but_other_traversal_is_rejected():
    assert builder.skip_dependency_file("../../Scripts/mcp.exe") == "installer_entrypoint"
    assert builder.skip_dependency_file("../../Scripts/__pycache__/pywin32_postinstall.cpython-312.pyc") == "generated_or_debug_file"
    assert builder.skip_dependency_file("package-1.dist-info/direct_url.json") == "local_installer_metadata"
    assert builder.skip_dependency_file("package-1.dist-info/licenses/LICENSE") is None
    for name in ("../../secret.txt", "../../Scripts/../credentials.py", "../../../Scripts/mcp.exe"):
        with pytest.raises(ValueError):
            builder.skip_dependency_file(name)


def test_record_verification_rejects_modified_data():
    data = b"verified package file"
    digest = "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
    builder.verify_record(data, digest, len(data), "fixture")
    with pytest.raises(ValueError, match="hash mismatch"):
        builder.verify_record(b"modified package file", digest, None, "fixture")
    with pytest.raises(ValueError, match="size mismatch"):
        builder.verify_record(data, digest, 1, "fixture")
    with pytest.raises(ValueError, match="Missing RECORD"):
        builder.verify_record(data, None, None, "fixture")


class FakeDistribution:
    def __init__(self, name, version="1.0", requires=()):
        self.metadata = Message()
        self.metadata["Name"] = name
        self.metadata["Version"] = version
        self.version = version
        self.requires = list(requires)


def test_resolves_platform_markers_and_requested_extras_without_model_extra():
    distributions = {
        "first": FakeDistribution("first", requires=["second[crypto]>=1", "torch; extra == 'model'",
                                                        "ignored; sys_platform == 'emscripten'"]),
        "second": FakeDistribution("second", requires=["crypto; extra == 'crypto'"]),
        "crypto": FakeDistribution("crypto"),
    }
    result = builder.dependency_closure(["first==1.0"], provider=distributions.__getitem__)
    assert list(result) == ["crypto", "first", "second"]


def test_dependency_constraint_is_checked_even_for_previously_visited_package():
    distributions = {"a": FakeDistribution("a", requires=["b>=1", "c"]),
                     "b": FakeDistribution("b"), "c": FakeDistribution("c", requires=["b>=2"])}
    with pytest.raises(ValueError, match="does not satisfy"):
        builder.dependency_closure(["a"], provider=distributions.__getitem__)


def test_model_and_direct_url_dependencies_fail_closed():
    with pytest.raises(ValueError, match="Model library"):
        builder.dependency_closure(["torch"])
    with pytest.raises(ValueError, match="Direct URL"):
        builder.dependency_closure(["example @ https://example.com/example.whl"])


def test_writer_rejects_case_insensitive_collisions(tmp_path):
    writer = builder.BundleWriter(tmp_path)
    writer.put("assets/Icon.png", b"one", "fixture")
    with pytest.raises(ValueError, match="Duplicate"):
        writer.put("assets/icon.png", b"two", "fixture")


def create_wheel(path, extra=None):
    metadata = b"Name: architecture-review-plugin\nVersion: 0.3.0a2\nRequires-Dist: pydantic==2.14.1\n\n"
    files = {"arch_review/__init__.py": b"__version__ = '0.3.0a2'\n",
             "architecture_review_plugin-0.3.0a2.dist-info/METADATA": metadata}
    files.update(extra or {})
    record_name = "architecture_review_plugin-0.3.0a2.dist-info/RECORD"
    record = io.StringIO()
    rows = [(name, "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode(),
             len(data)) for name, data in files.items()]
    csv.writer(record).writerows([*rows, (record_name, "", "")])
    files[record_name] = record.getvalue().encode()
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return path


def test_engine_wheel_record_and_payload_are_verified(tmp_path):
    path = create_wheel(tmp_path / "engine.whl")
    parsed, files = builder.wheel_contents(path)
    assert parsed["Version"] == "0.3.0a2"
    assert "arch_review/__init__.py" in files
    unsafe = create_wheel(tmp_path / "unsafe.whl", {"training/private.jsonl": b"not public"})
    with pytest.raises(ValueError, match="Unexpected engine wheel payload"):
        builder.wheel_contents(unsafe)
    weights = create_wheel(tmp_path / "weights.whl", {"arch_review/model.safetensors": b"weights"})
    with pytest.raises(ValueError, match="Unexpected engine package resource"):
        builder.wheel_contents(weights)


def test_engine_wheel_fails_when_payload_does_not_match_record(tmp_path):
    original = create_wheel(tmp_path / "source.whl")
    modified = tmp_path / "modified.whl"
    with zipfile.ZipFile(original) as source, zipfile.ZipFile(modified, "w") as target:
        for info in source.infolist():
            data = source.read(info)
            target.writestr(info, b"modified" if info.filename.endswith("__init__.py") else data)
    with pytest.raises(ValueError, match="RECORD .* mismatch"):
        builder.wheel_contents(modified)


def installed_fixture(root, include_license=True):
    files = {"example.py": b"VALUE = 1\n", "example-1.0.dist-info/METADATA": b"Name: example\nVersion: 1.0\n",
             "example-1.0.dist-info/direct_url.json": b'{"url": "file:///private/developer/path"}',
             "example-1.0.dist-info/INSTALLER": b"test installer"}
    if include_license:
        files["example-1.0.dist-info/licenses/LICENSE"] = b"Example permission notice"
    rows = []
    for name, data in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
        rows.append((name, "sha256=" + digest, len(data)))
    record_path = "example-1.0.dist-info/RECORD"
    with (root / record_path).open("w", newline="", encoding="utf-8") as stream:
        csv.writer(stream).writerows([*rows, (record_path, "", ""), ("../../Scripts/example.exe", "", "")])
    return metadata.PathDistribution(root / "example-1.0.dist-info")


def test_installed_copy_scrubs_local_paths_and_retains_licenses_with_valid_records(tmp_path):
    distribution = installed_fixture(tmp_path / "source")
    writer = builder.BundleWriter(tmp_path / "destination")
    result = builder.copy_dependency(writer, "example", distribution)
    assert result["record_hashes_verified"]
    assert result["licenses"] == ["runtime/Lib/site-packages/example-1.0.dist-info/licenses/LICENSE"]
    assert not any("direct_url.json" in name or name.endswith("INSTALLER") for name in writer.files)
    assert not any("Scripts/" in name for name in writer.files)
    record = (writer.root / "runtime/Lib/site-packages/example-1.0.dist-info/RECORD").read_text()
    assert "direct_url" not in record
    assert "../../" not in record
    for name, digest, size in csv.reader(io.StringIO(record)):
        if not name.endswith("/RECORD"):
            builder.verify_record((writer.root / "runtime/Lib/site-packages" / name).read_bytes(),
                                  digest, size, name)


def test_installed_copy_rejects_tampering_and_missing_license(tmp_path):
    distribution = installed_fixture(tmp_path / "source")
    (tmp_path / "source/example.py").write_bytes(b"CHANGED = 2\n")
    with pytest.raises(ValueError, match="RECORD .* mismatch"):
        builder.copy_dependency(builder.BundleWriter(tmp_path / "modified"), "example", distribution)
    unlicensed = installed_fixture(tmp_path / "unlicensed", include_license=False)
    with pytest.raises(ValueError, match="No installed license"):
        builder.copy_dependency(builder.BundleWriter(tmp_path / "no-license"), "example", unlicensed)
