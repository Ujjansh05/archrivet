"""Private stdio driver for the browser smoke test; never opens a real window."""
import json
import sys
from importlib.resources import files

from arch_review.diagram import ViewerManager

views = ViewerManager()
examples = json.loads(files("arch_review").joinpath("data/viewer_demo.json").read_text(encoding="utf-8"))
view = views.create(examples[0])


def reply(value):
    print(json.dumps(value), flush=True)


reply(view)
try:
    for line in sys.stdin:
        command = json.loads(line)
        if command["action"] == "update":
            graph = command.get("diagram", examples[command.get("example", 0)])
            view = views.update(view["view_id"], graph, view["revision"])
        elif command["action"] == "close":
            view = views.close(view["view_id"])
        elif command["action"] == "open":
            views._launch = lambda _: False
            view = views.open(view["view_id"])
        elif command["action"] == "shutdown":
            break
        else:
            raise ValueError("Unknown smoke-test command")
        reply(view)
finally:
    views.shutdown()
