"""Repackage an audited ArchRivet rules bundle as a Windows Claude Code plugin."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "extensions" / "claude-code"
STATIC_FILES = (
    ".claude-plugin/plugin.json",
    ".mcp.json",
    "launch.py",
    "README.md",
    "skills/review-architecture/SKILL.md",
)
PASS_FILES = {
    "LICENSE",
    "PRIVACY.md",
    "TERMS.md",
    "THIRD_PARTY_NOTICES.md",
    "bundle-config.json",
    "audit/dependencies.json",
}
PASS_PREFIXES = ("assets/", "icons/", "runtime/", "server/")


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verified_source_files(source: Path) -> list[str]:
    source = source.resolve(strict=True)
    if not source.is_dir():
        raise ValueError("Source bundle must be a directory")
    inventory = json.loads((source / "audit/files.json").read_text(encoding="utf-8"))
    if inventory.get("format") != "archrivet-file-inventory-v1":
        raise ValueError("Unexpected source inventory format")
    names: set[str] = set()
    for entry in inventory["files"]:
        name = entry["path"]
        member = (source / name).resolve(strict=True)
        if (not member.is_relative_to(source) or not member.is_file() or name in names
                or "\\" in name or name.startswith("/") or ".." in Path(name).parts):
            raise ValueError(f"Unsafe or duplicate source member: {name}")
        if member.stat().st_size != entry["bytes"] or digest(member) != entry["sha256"]:
            raise ValueError(f"Source inventory mismatch: {name}")
        names.add(name)
    actual = {path.relative_to(source).as_posix() for path in source.rglob("*") if path.is_file()}
    if actual != names | {"audit/files.json"}:
        raise ValueError("Source bundle has missing or unexpected files")
    required = {"runtime/python.exe", "server/main.py", "bundle-config.json", "audit/dependencies.json"}
    if not required.issubset(names):
        raise ValueError("Source bundle lacks runtime, server or audit data")
    config = json.loads((source / "bundle-config.json").read_text(encoding="utf-8"))
    if config.get("variant") != "rules":
        raise ValueError("Claude Code preview only packages the audited rules engine")
    return sorted(name for name in names if name in PASS_FILES or name.startswith(PASS_PREFIXES))


def build(source_bundle: Path, output: Path) -> dict:
    source = source_bundle.resolve(strict=True)
    output = output.resolve()
    if output.exists():
        raise ValueError("Output directory exists; choose a fresh path")
    if output.is_relative_to(source) or source.is_relative_to(output):
        raise ValueError("Output and source must not overlap")
    source_files = verified_source_files(source)
    manifest = json.loads((TEMPLATE / STATIC_FILES[0]).read_text(encoding="utf-8"))
    version = manifest["version"]
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?", version):
        raise ValueError("Invalid plugin version")
    config = json.loads((source / "bundle-config.json").read_text(encoding="utf-8"))
    if version != config["extension_version"]:
        raise ValueError("Plugin and runtime versions differ")
    for name in STATIC_FILES:
        if not (TEMPLATE / name).is_file():
            raise ValueError(f"Missing Claude Code source: {name}")
    if any(name.endswith((".safetensors", ".pt")) for name in source_files):
        raise ValueError("Model weights are outside this preview")

    plugin = output / "archrivet"
    plugin.mkdir(parents=True, exist_ok=False)
    files: dict[str, dict] = {}
    for name, origin in [(name, TEMPLATE / name) for name in STATIC_FILES] + [
        (name, source / name) for name in source_files
    ]:
        target = plugin / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(origin, target)
        files[name] = {"path": name, "bytes": target.stat().st_size, "sha256": digest(target)}
    inventory_path = plugin / "audit" / "claude-files.json"
    inventory_path.write_text(json.dumps({"format": "archrivet-claude-file-inventory-v1",
                                          "files": [files[name] for name in sorted(files)]},
                                         indent=2) + "\n", encoding="utf-8")
    archive_path = output / f"archrivet-claude-code-windows-x64-{version}.zip"
    with zipfile.ZipFile(archive_path, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(plugin.rglob("*")):
            if not path.is_file():
                continue
            name = "archrivet/" + path.relative_to(plugin).as_posix()
            info = zipfile.ZipInfo(name, date_time=(2026, 10, 18, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            with path.open("rb") as stream, archive.open(info, "w", force_zip64=True) as target:
                shutil.copyfileobj(stream, target, 1024 * 1024)
    report = {"format": "archrivet-claude-build-v1", "version": version,
              "plugin_directory": str(plugin), "archive": str(archive_path),
              "archive_bytes": archive_path.stat().st_size, "archive_sha256": digest(archive_path),
              "file_count": len(files) + 1, "model_weights_included": False,
              "claude_host_tested": False, "publication_performed": False}
    (output / "build-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-bundle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.source_bundle, args.output), indent=2))


if __name__ == "__main__":
    main()
