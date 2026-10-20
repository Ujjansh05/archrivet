"""Scripted viewer walkthrough: demonstrates transport/UI, not model performance."""
import json
import time
from importlib.resources import files

from .diagram import Diagram, ViewerManager


def run_demo(*, open_browser=True, animate=False, duration=0):
    examples = json.loads(files("arch_review").joinpath("data/viewer_demo.json").read_text(encoding="utf-8"))
    views = ViewerManager()
    try:
        result = views.create(Diagram.model_validate(examples[0]), open_browser=open_browser)
        print("ArchRivet live diagram preview (scripted example, no model or training).", flush=True)
        print("Open this private local link if no browser appears:", flush=True)
        print(result["url"], flush=True)
        print("Close the browser at any time. Ctrl+C here stops the preview server.", flush=True)
        started = time.monotonic()
        index = 1
        while not duration or time.monotonic() - started < duration:
            if animate and index < len(examples) and time.monotonic() - started >= index * 8:
                result = views.update(result["view_id"], Diagram.model_validate(examples[index]), result["revision"])
                print(f"Published diagram revision {result['revision']}: {examples[index]['title']}", flush=True)
                index += 1
            time.sleep(.2)
    except KeyboardInterrupt:
        print("\nViewer stopped. Reviews and training are unaffected.", flush=True)
    finally:
        views.shutdown()
