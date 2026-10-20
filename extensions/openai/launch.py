"""Launch the bundled Windows rules server without installers or model downloads."""
import json
import multiprocessing
import os
import sys
from pathlib import Path


def main():
    root = Path(__file__).resolve().parent
    if os.name != "nt":
        raise RuntimeError("This ArchRivet package supports Windows x64 only")
    # -I ignores user-site/PYTHONPATH; these are package-owned paths only.
    sys.path.insert(0, str(root / "runtime" / "Lib" / "site-packages"))
    sys.path.insert(0, str(root / "server"))
    config = json.loads((root / "bundle-config.json").read_text(encoding="utf-8"))
    if config["variant"] != "rules":
        raise RuntimeError("This OpenAI package must use its bundled rules engine")
    # Keep this release independent of old extension/model opt-ins and checkpoints.
    os.environ["ARCHRIVET_ENABLE_LAYA"] = "false"
    os.environ.pop("ARCHRIVET_MODEL_DIR", None)
    os.environ["ARCHRIVET_EXTENSION_HOME"] = str(Path.home() / ".archrivet-openai")
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["PYTHONUTF8"] = "1"
    from main import main as run_server

    # Keep the MCP version aligned with this standalone package candidate.
    sys.modules["main"].VERSION = config["extension_version"]
    run_server()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
