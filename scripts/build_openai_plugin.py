"""Build an offline Windows x64 local-MCP preview ZIP; never publish or download.

Run with the audited Windows Python 3.12 environment containing the engine's
dependencies. Only the non-model dependency closure is copied. Installed files
are checked against RECORD before use; local installer provenance is omitted.
The output is a submission candidate, not evidence of OpenAI approval.
"""
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
import json
import platform
import re
import sys
import zipfile
from collections import deque
from email.parser import BytesParser
from importlib import metadata
from pathlib import Path, PurePosixPath

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[1]
SOURCE_FILES = (
    "plugin.json", "mcp.json", "launch.py", "README.md",
    "assets/icon.png", "assets/screenshot.png",
)
POLICY_FILES = ("LICENSE", "THIRD_PARTY_NOTICES.md", "PRIVACY.md", "TERMS.md")
RUNTIME_FILES = (
    "python.exe", "python3.dll", "python312.dll", "vcruntime140.dll",
    "vcruntime140_1.dll", "LICENSE.txt",
)
MODEL_PACKAGES = {
    "laya", "torch", "torchvision", "torchaudio", "transformers", "tokenizers",
    "safetensors", "numpy", "huggingface-hub", "triton",
}
SKIP_DIRECTORIES = {"__pycache__", "site-packages", "test", "tests", "ensurepip", "idlelib", "tkinter",
                    "turtledemo", "__phello__"}
LOCAL_METADATA = {"direct_url.json", "INSTALLER", "REQUESTED", "uv_cache.json"}
HASH_ALGORITHMS = {"sha256", "sha384", "sha512"}
RUNTIME_LICENSE_COMPONENTS = ("openssl", "libffi", "xz")


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def safe_member(name):
    """Reject paths that can escape or alias differently when extracted on Windows."""
    path = PurePosixPath(name)
    if (not name or "\\" in name or path.is_absolute() or path.as_posix() != name
            or any(part in {"", ".", ".."} or re.search(r'[<>:"|?*\x00-\x1f]', part)
                   or part.endswith((".", " "))
                   for part in path.parts)):
        raise ValueError(f"Unsafe package path: {name!r}")
    for part in path.parts:
        stem = part.split(".", 1)[0].upper()
        if stem in {"CON", "PRN", "AUX", "NUL"} or re.fullmatch(r"(?:COM|LPT)[1-9]", stem):
            raise ValueError(f"Reserved Windows package path: {name!r}")
    return path


def inside_file(root, relative):
    """Allow only existing regular files, with no symlink/junction traversal."""
    relative = safe_member(str(relative).replace("\\", "/"))
    root = Path(root).resolve(strict=True)
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink() or (hasattr(current, "is_junction") and current.is_junction()):
            raise ValueError(f"Linked input is not allowed: {relative}")
    resolved = current.resolve(strict=True)
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise ValueError(f"Not a regular file within the input root: {relative}")
    return resolved


def verify_record(data, expected_hash, expected_size, description):
    if expected_size is not None and int(expected_size) != len(data):
        raise ValueError(f"RECORD size mismatch: {description}")
    if not expected_hash:
        raise ValueError(f"Missing RECORD hash: {description}")
    algorithm, encoded = expected_hash.split("=", 1)
    if algorithm not in HASH_ALGORITHMS:
        raise ValueError(f"Unsupported RECORD hash: {description}")
    actual = base64.urlsafe_b64encode(hashlib.new(algorithm, data).digest()).rstrip(b"=").decode("ascii")
    if actual != encoded:
        raise ValueError(f"RECORD hash mismatch: {description}")


def skip_dependency_file(name):
    """Only known installer entry points may leave site-packages; none are copied."""
    normalized = name.replace("\\", "/")
    if ".." in PurePosixPath(normalized).parts:
        if re.fullmatch(r"\.\./\.\./Scripts/[A-Za-z0-9_.-]+\.(?:exe|py)", normalized):
            return "installer_entrypoint"
        if re.fullmatch(r"\.\./\.\./Scripts/__pycache__/[A-Za-z0-9_.-]+\.pyc", normalized):
            return "generated_or_debug_file"
        raise ValueError(f"Unexpected installed file outside site-packages: {name}")
    safe_member(normalized)
    path = PurePosixPath(normalized)
    if "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo", ".pdb"}:
        return "generated_or_debug_file"
    if path.name in LOCAL_METADATA:
        return "local_installer_metadata"
    if path.name == "RECORD" and path.parent.name.endswith(".dist-info"):
        return "regenerated_record"
    return None


def dependency_closure(requirements, provider=metadata.distribution, environment=None):
    """Resolve installed versions, including transitive extras and platform markers."""
    environment = dict(environment or default_environment())
    pending = deque((Requirement(value), "") for value in requirements)
    visited = set()
    result = {}
    while pending:
        requirement, parent_extra = pending.popleft()
        marker_environment = {**environment, "extra": parent_extra}
        if requirement.marker and not requirement.marker.evaluate(marker_environment):
            continue
        if requirement.url:
            raise ValueError(f"Direct URL dependencies are not accepted: {requirement.name}")
        name = canonicalize_name(requirement.name)
        if name in MODEL_PACKAGES:
            raise ValueError(f"Model library is forbidden in this Rules package: {name}")
        distribution = provider(name)
        if canonicalize_name(distribution.metadata["Name"]) != name:
            raise ValueError(f"Installed distribution name mismatch: {name}")
        if not requirement.specifier.contains(distribution.version, prereleases=True):
            raise ValueError(f"Installed {name}=={distribution.version} does not satisfy {requirement}")
        python_requirement = distribution.metadata.get("Requires-Python")
        if python_requirement:
            from packaging.specifiers import SpecifierSet
            if not SpecifierSet(python_requirement).contains(environment["python_full_version"]):
                raise ValueError(f"Incompatible Python requirement for {name}: {python_requirement}")
        result[name] = distribution
        for extra in ("", *sorted(requirement.extras)):
            if (name, extra) in visited:
                continue
            visited.add((name, extra))
            pending.extend((Requirement(value), extra) for value in distribution.requires or [])
    return dict(sorted(result.items()))


class BundleWriter:
    def __init__(self, root):
        self.root = Path(root)
        self.files = {}
        self.names = set()

    def put(self, name, data, component):
        safe_member(name)
        key = name.casefold()
        if key in self.names:
            raise ValueError(f"Duplicate bundle path: {name}")
        target = self.root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        self.names.add(key)
        self.files[name] = {"path": name, "bytes": len(data), "sha256": sha256(data), "component": component}

    def copy(self, root, relative, destination, component):
        self.put(destination, inside_file(root, relative).read_bytes(), component)

    def json(self, name, value, component="build_audit"):
        self.put(name, (json.dumps(value, indent=2, sort_keys=True) + "\n").encode(), component)


def wheel_contents(wheel):
    """Load only a verified engine wheel with no arbitrary scripts or data payloads."""
    with zipfile.ZipFile(wheel) as archive:
        paths = {}
        keys = set()
        if len(archive.infolist()) > 5000 or sum(info.file_size for info in archive.infolist()) > 75 * 1024**2:
            raise ValueError("Engine wheel exceeds the source-only package size limit")
        for info in archive.infolist():
            if info.is_dir():
                continue
            safe_member(info.filename)
            if info.filename.casefold() in keys or (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("Duplicate or linked wheel file")
            keys.add(info.filename.casefold())
            if info.file_size > 20 * 1024 * 1024:
                raise ValueError("Oversized engine wheel member")
            paths[info.filename] = archive.read(info)
        metas = [path for path in paths if path.endswith(".dist-info/METADATA")]
        if len(metas) != 1:
            raise ValueError("Expected one engine wheel METADATA file")
        parsed = BytesParser().parsebytes(paths[metas[0]])
        if canonicalize_name(parsed["Name"] or "") != "architecture-review-plugin":
            raise ValueError("Expected the ArchRivet engine wheel")
        dist_info = str(PurePosixPath(metas[0]).parent)
        record_path = dist_info + "/RECORD"
        if record_path not in paths:
            raise ValueError("Engine wheel has no RECORD")
        record = {}
        for name, digest, size in csv.reader(io.StringIO(paths[record_path].decode("utf-8"))):
            if name in record:
                raise ValueError("Duplicate engine RECORD row")
            record[name] = (digest, size)
        if set(record) != set(paths):
            raise ValueError("Engine RECORD does not match wheel members")
        for name, data in paths.items():
            relative = PurePosixPath(name)
            if relative.parts[0] not in {"arch_review", dist_info}:
                raise ValueError(f"Unexpected engine wheel payload: {name}")
            if relative.parts[0] == "arch_review" and relative.suffix not in {
                ".py", ".json", ".jsonl", ".html", ".css", ".js",
            }:
                raise ValueError(f"Unexpected engine package resource: {name}")
            if name != record_path:
                digest, size = record[name]
                verify_record(data, digest, size, name)
    return parsed, paths


def copy_dependency(writer, name, distribution):
    files = distribution.files
    if not files:
        raise ValueError(f"Distribution has no file manifest: {name}")
    root = Path(distribution.locate_file("")).resolve(strict=True)
    records = [str(path).replace("\\", "/") for path in files
               if str(path).endswith(".dist-info/RECORD")]
    if len(records) != 1:
        raise ValueError(f"Expected one installed RECORD for {name}")
    original_record = inside_file(root, records[0]).read_bytes()
    copied = []
    skipped = []
    licenses = []
    for path in sorted(files, key=str):
        relative = str(path).replace("\\", "/")
        reason = skip_dependency_file(relative)
        if reason:
            skipped.append({"path": relative, "reason": reason})
            continue
        data = inside_file(root, relative).read_bytes()
        digest = str(path.hash.mode) + "=" + str(path.hash.value) if path.hash else None
        verify_record(data, digest, path.size, name + "/" + relative)
        destination = "runtime/Lib/site-packages/" + relative
        writer.put(destination, data, name)
        copied.append((relative, "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(data).digest())
                       .rstrip(b"=").decode("ascii"), str(len(data))))
        if any(token in part.lower() for part in PurePosixPath(relative).parts
               for token in ("license", "copying", "notice")):
            licenses.append(destination)
    if not licenses:
        raise ValueError(f"No installed license text found for {name}; review before bundling")
    record = io.StringIO(newline="")
    csv.writer(record, lineterminator="\n").writerows([*copied, (records[0], "", "")])
    writer.put("runtime/Lib/site-packages/" + records[0], record.getvalue().encode(), name)
    return {"name": name, "version": distribution.version, "licenses": licenses,
            "license_expression": distribution.metadata.get("License-Expression"),
            "copied_files": len(copied) + 1, "omitted_files": skipped,
            "source_record_sha256": sha256(original_record), "record_hashes_verified": True}


def copy_runtime(writer, base, source):
    for name in RUNTIME_FILES:
        writer.copy(base, name, "runtime/" + name, "cpython")
    for directory in ("Lib", "DLLs"):
        for path in sorted((base / directory).rglob("*")):
            relative = path.relative_to(base).as_posix()
            if SKIP_DIRECTORIES.intersection(path.relative_to(base).parts):
                continue
            if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
                raise ValueError(f"Runtime links are not allowed: {relative}")
            if not path.is_file() or path.suffix in {".pyc", ".pyo", ".pdb"}:
                continue
            if directory == "DLLs":
                if path.name in {"py.ico", "pyc.ico", "pyd.ico", "python_lib.cat"}:
                    # CPython installer resources; the portable runtime does not load them.
                    continue
                if path.suffix not in {".dll", ".pyd"}:
                    raise ValueError(f"Unexpected runtime DLL resource: {relative}")
                if path.name.startswith(("_test", "_ctypes_test", "tcl", "tk", "_tkinter")):
                    continue
            writer.copy(base, relative, "runtime/" + relative, "cpython")
    included = []
    license_root = source / "runtime-licenses"
    if license_root.is_dir():
        for path in sorted(license_root.iterdir()):
            if not re.fullmatch(r"[A-Za-z0-9_-]+\.(?:txt|md)", path.name):
                raise ValueError(f"Unexpected runtime license filename: {path.name}")
            destination = "runtime/licenses/" + path.name
            writer.copy(license_root, path.name, destination, "runtime_licenses")
            included.append(path.stem.lower())
    missing = [component for component in RUNTIME_LICENSE_COMPONENTS if component not in included]
    return {"python_version": platform.python_version(), "architecture": "windows-x64",
            "runtime_license": "runtime/LICENSE.txt", "supplemental_notices": included,
            "runtime_license_review_pending": missing,
            "excluded": sorted(SKIP_DIRECTORIES) + ["pythonw.exe", "Scripts", "include", "libs", "tcl",
                                                       "test_extension_modules", "debug_symbols"]}


def build(wheel, output, runtime_base=None, root=ROOT):
    if sys.platform != "win32" or sys.version_info[:2] != (3, 12) or sys.maxsize < 2**32:
        raise ValueError("Build using the audited Windows x64 Python 3.12 environment")
    wheel = Path(wheel).resolve(strict=True)
    output = Path(output).resolve()
    base = Path(runtime_base or sys.base_prefix).resolve(strict=True)
    root = Path(root).resolve(strict=True)
    source = root / "extensions/openai"
    # Refuse existing output; no cleanup or mutation of earlier artifacts.
    if output.exists():
        raise ValueError("Output directory already exists; select a new build directory")
    if base != Path(sys.base_prefix).resolve():
        raise ValueError("Runtime base must match this interpreter's base to preserve binary compatibility")
    if output.is_relative_to(base):
        raise ValueError("Output must not be inside the interpreter being packaged")
    parsed, engine_files = wheel_contents(wheel)
    dependencies = dependency_closure(parsed.get_all("Requires-Dist", []))
    manifest = json.loads(inside_file(source, "plugin.json").read_text(encoding="utf-8"))
    version = manifest["version"]
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?", version):
        raise ValueError("Plugin version must be an explicit semantic version")
    # Fail before copying a runtime if the required public assets/policies are absent.
    for name in SOURCE_FILES:
        inside_file(source, name)
    for name in POLICY_FILES:
        inside_file(root, name)
    output.mkdir(parents=True, exist_ok=False)
    staging = output / "bundle"
    staging.mkdir()
    writer = BundleWriter(staging)
    for name in SOURCE_FILES:
        writer.copy(source, name, name, "archrivet_plugin")
    for name in POLICY_FILES:
        writer.copy(root, name, name, "archrivet_plugin")
    desktop = root / "extensions/desktop"
    for name in ("server/main.py", "server/setup_model.py", "icons/icon-128.png"):
        writer.copy(desktop, name, name, "archrivet_plugin")
    runtime = copy_runtime(writer, base, source)
    for name, data in sorted(engine_files.items()):
        writer.put("runtime/Lib/site-packages/" + name, data, "architecture-review-plugin")
    packages = [copy_dependency(writer, name, distribution) for name, distribution in dependencies.items()]
    writer.json("bundle-config.json", {"variant": "rules", "engine_version": parsed["Version"],
                                       "extension_version": version})
    dependency_report = {
        "format": "archrivet-dependency-inventory-v1", "model_packages_included": False,
        "python": runtime, "packages": packages,
        "engine": {"name": parsed["Name"], "version": parsed["Version"], "wheel_sha256": sha256(wheel.read_bytes())},
        "notes": ["Installed RECORD hashes were checked; bundled RECORDs omit removed installer files.",
                  "License inventory is not a legal review or an OpenAI certification.",
                  "Engine-wheel data includes existing public evidence and evaluation fixtures.",
                  "Private training workspaces are not build inputs; model weights and local installer paths are excluded."]}
    writer.json("audit/dependencies.json", dependency_report)
    writer.json("audit/files.json", {"format": "archrivet-file-inventory-v1",
                                     "excluded_from_inventory": ["audit/files.json"],
                                     "files": [writer.files[name] for name in sorted(writer.files)]})
    artifact = output / f"archrivet-openai-windows-x64-{version}.zip"
    with zipfile.ZipFile(artifact, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name in sorted(writer.files):
            info = zipfile.ZipInfo(name, date_time=(2026, 10, 17, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, (staging / name).read_bytes(), compresslevel=6)
    report = {"format": "archrivet-openai-build-audit-v1", "artifact": artifact.name,
              "artifact_sha256": sha256(artifact.read_bytes()), "artifact_bytes": artifact.stat().st_size,
              "uncompressed_bytes": sum(item["bytes"] for item in writer.files.values()),
              "file_count": len(writer.files), "dependency_count": len(packages),
              "plugin_version": version, "engine_version": parsed["Version"],
              "engine_wheel_sha256": sha256(wheel.read_bytes()),
              "runtime_license_review_pending": runtime["runtime_license_review_pending"],
              "relocated_clean_launch_verified": False, "chatgpt_desktop_installation_verified": False,
              "official_schema_validation_performed": False, "openai_approval_verified": False,
              "publication_performed": False, "training_started": False, "model_downloaded": False}
    (output / "build-audit.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runtime-base", type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.wheel, args.output, args.runtime_base), indent=2))


if __name__ == "__main__":
    main()
