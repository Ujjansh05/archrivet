"""Offline checks for the prepared OpenAI package's submission metadata."""
import importlib.util
import json
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "extensions" / "openai"
SPEC = importlib.util.spec_from_file_location(
    "archrivet_openai_metadata_validator", ROOT / "scripts" / "validate_openai_plugin.py")
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


@pytest.fixture
def package(tmp_path):
    """Metadata validation needs no interpreter installation or executable launch."""
    destination = tmp_path / "bundle"
    destination.mkdir()
    for name in ("plugin.json", "mcp.json"):
        shutil.copyfile(SOURCE / name, destination / name)
    shutil.copytree(SOURCE / "assets", destination / "assets")
    return destination


def edit_manifest(package, edit):
    path = package / "plugin.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    edit(value["extensions"]["com.openai"])
    path.write_text(json.dumps(value), encoding="utf-8")


def test_valid_metadata_does_not_claim_portal_approval_or_schema_check(package):
    result = validator.validate_metadata(package)
    assert result["manifest"]["name"] == "archrivet"
    assert result["review_test_cases_included"] is False
    assert result["portable_schema_validated"] is False
    assert result["openai_portal_validation_performed"] is False
    assert not result.get("submission_ready", False)
    assert not result.get("real_ai_host_tested", False)


@pytest.mark.parametrize("bad_path", ["../outside.png", "./../outside.png", "C:/private/icon.png"])
def test_asset_traversal_is_rejected_before_reading_outside_file(package, bad_path, monkeypatch):
    outside = package.parent / "outside.png"
    outside.write_bytes(b"private test sentinel")
    edit_manifest(package, lambda ext: ext["interface"].update(logo=bad_path))
    original_read_bytes = Path.read_bytes

    def guarded_read_bytes(path):
        assert path.resolve() != outside.resolve(), "Validator read an out-of-package asset"
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", guarded_read_bytes)
    with pytest.raises(ValueError, match="Asset"):
        validator.validate_metadata(package)


@pytest.mark.parametrize("field,maximum", [
    ("displayName", 30), ("shortDescription", 30), ("developerName", 80), ("longDescription", 4000)])
def test_oversized_listing_field_is_rejected(package, field, maximum):
    edit_manifest(package, lambda ext: ext["interface"].update({field: "x" * (maximum + 1)}))
    with pytest.raises(ValueError, match="listing text length"):
        validator.validate_metadata(package)


def add_review_cases(ext):
    ext["review"]["test_cases"] = {
        "positive": [{"description": "case", "prompt": "test", "tools_triggered": "tool",
                      "expected_behavior": "result"} for _ in range(5)],
        "negative": [{"description": "case", "prompt": "test"} for _ in range(3)],
    }


def test_review_cases_are_validated_if_present(package):
    edit_manifest(package, add_review_cases)
    result = validator.validate_metadata(package)
    assert result["review_test_cases_included"] is True


def test_missing_positive_case_is_rejected(package):
    def edit(ext):
        add_review_cases(ext)
        ext["review"]["test_cases"]["positive"].pop()

    edit_manifest(package, edit)
    with pytest.raises(ValueError, match="exactly five"):
        validator.validate_metadata(package)


@pytest.mark.parametrize("field", ["tools_triggered", "expected_behavior"])
def test_positive_case_requires_tools_and_observable_result(package, field):
    def edit(ext):
        add_review_cases(ext)
        ext["review"]["test_cases"]["positive"][0].pop(field)

    edit_manifest(package, edit)
    with pytest.raises(ValueError, match="Incomplete positive case"):
        validator.validate_metadata(package)


def test_listing_urls_reject_embedded_credentials(package):
    edit_manifest(package, lambda ext: ext["interface"].update(
        supportURL="https://secret:token@example.invalid/support"))
    with pytest.raises(ValueError, match="public HTTPS URL"):
        validator.validate_metadata(package)


def test_unexpected_launch_command_is_not_accepted(package):
    path = package / "mcp.json"
    config = json.loads(path.read_text(encoding="utf-8"))
    config["mcpServers"]["archrivet"]["args"].append("--unexpected")
    path.write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(ValueError, match="Unexpected launch command"):
        validator.validate_metadata(package)


@pytest.mark.parametrize("field", ["test_credentials", "reviewer_instructions"])
def test_reviewer_private_access_fields_are_rejected(package, field):
    edit_manifest(package, lambda ext: ext["review"].update({field: "synthetic private field"}))
    with pytest.raises(ValueError, match="Reviewer access"):
        validator.validate_metadata(package)


def test_optional_downloaded_official_schemas_are_used_without_network(package):
    pytest.importorskip("jsonschema")
    schemas = ROOT / ".runtime" / "openai-schemas"
    if not all((schemas / (name + ".schema.json")).is_file() for name in ("plugin", "mcp")):
        pytest.skip("Official schemas were not previously downloaded; tests never fetch them")
    result = validator.validate_metadata(package, schemas)
    assert result["portable_schema_validated"] is True
    assert result["openai_portal_validation_performed"] is False

