"""Bounded, memory-only architecture diagrams and their local read-only viewer.

This service does not share the model API, execute diagram markup, or accept
browser mutations. The assistant updates diagrams through the MCP process.
"""

from __future__ import annotations

import hmac
import json
import secrets
import threading
import webbrowser
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from typing import Annotated, Any, Literal
from urllib.parse import parse_qs, urlencode, urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

Identifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$", max_length=64)]


class _DiagramModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)


class DiagramNode(_DiagramModel):
    id: Identifier
    label: str = Field(min_length=1, max_length=100)
    kind: Literal["client", "service", "database", "queue", "cache", "external", "group"] = "service"
    detail: str = Field(default="", max_length=1000)
    state: Literal["proposed", "existing", "unknown"] = "proposed"


class DiagramEdge(_DiagramModel):
    id: Identifier
    source: Identifier
    target: Identifier
    label: str = Field(default="", max_length=100)


class Diagram(_DiagramModel):
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    nodes: list[DiagramNode] = Field(min_length=1, max_length=80)
    edges: list[DiagramEdge] = Field(default_factory=list, max_length=160)

    @model_validator(mode="after")
    def valid_references(self) -> Diagram:
        node_ids = [node.id for node in self.nodes]
        edge_ids = [edge.id for edge in self.edges]
        if len(set(node_ids)) != len(node_ids):
            raise ValueError("Node IDs must be unique within a diagram.")
        if len(set(edge_ids)) != len(edge_ids):
            raise ValueError("Edge IDs must be unique within a diagram.")
        known = set(node_ids)
        if any(edge.source not in known or edge.target not in known for edge in self.edges):
            raise ValueError("Every edge endpoint must reference a node in this diagram.")
        return self


class RevisionConflict(ValueError):
    """The assistant tried to replace a revision it has not read."""


class ViewerLimitError(ValueError):
    """All available view slots contain active diagrams."""


@dataclass
class _View:
    view_id: str
    token: str
    diagram: Diagram
    revision: int
    active: bool
    changes: dict[str, list[str]]
    updated_at: str


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _changes(before: Diagram | None, after: Diagram) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for name in ("nodes", "edges"):
        old = {} if before is None else {item.id: item.model_dump() for item in getattr(before, name)}
        new = {item.id: item.model_dump() for item in getattr(after, name)}
        result[f"added_{name}"] = sorted(new.keys() - old.keys())
        result[f"removed_{name}"] = sorted(old.keys() - new.keys())
        result[f"changed_{name}"] = sorted(key for key in old.keys() & new.keys() if old[key] != new[key])
    return result


class _ViewerHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False
    request_queue_size = 16

    def __init__(self, manager: ViewerManager):
        self.manager = manager
        self._connections = threading.BoundedSemaphore(16)
        super().__init__(("127.0.0.1", 0), _ViewerHandler)

    def process_request(self, request: Any, client_address: Any) -> None:
        if not self._connections.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._connections.release()
            raise

    def process_request_thread(self, request: Any, client_address: Any) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._connections.release()


class _ViewerHandler(BaseHTTPRequestHandler):
    server: _ViewerHTTPServer
    server_version = "ArchRivetViewer"
    sys_version = ""

    def setup(self) -> None:
        self.request.settimeout(5)
        super().setup()

    def log_message(self, format: str, *args: Any) -> None:
        # MCP stdio must stay protocol-only. Never log view IDs or credentials.
        pass

    def _respond(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; font-src 'self'; "
            "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'",
        )
        self.end_headers()
        if self.command != "HEAD":
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def _json(self, status: int, value: dict[str, Any]) -> None:
        self._respond(status, json.dumps(value, ensure_ascii=True).encode("utf-8"), "application/json; charset=utf-8")

    def _valid_origin(self) -> bool:
        origin = f"http://127.0.0.1:{self.server.server_port}"
        hosts = self.headers.get_all("Host", [])
        origins = self.headers.get_all("Origin", [])
        if hosts != [f"127.0.0.1:{self.server.server_port}"]:
            return False
        if origins and origins != [origin]:
            return False
        return self.headers.get("Sec-Fetch-Site", "none") in {"same-origin", "none"}

    def do_GET(self) -> None:
        if not self._valid_origin():
            self._json(403, {"error": "Only same-origin loopback requests are supported."})
            return
        if len(self.path) > 2048:
            self._json(414, {"error": "Request target is too long."})
            return
        try:
            parsed = urlsplit(self.path)
        except ValueError:
            self._json(400, {"error": "Invalid request target."})
            return
        if parsed.scheme or parsed.netloc or parsed.fragment:
            self._json(400, {"error": "Invalid request target."})
            return
        if parsed.path == "/api/state":
            query = parse_qs(parsed.query, keep_blank_values=True)
            if set(query) != {"view"} or len(query["view"]) != 1:
                self._json(400, {"error": "One view ID is required."})
                return
            authorizations = self.headers.get_all("Authorization", [])
            if len(authorizations) != 1 or not authorizations[0].startswith("Bearer "):
                self._json(401, {"error": "A valid view token is required."})
                return
            snapshot = self.server.manager._authorized_snapshot(query["view"][0], authorizations[0][7:])
            if snapshot is None:
                self._json(401, {"error": "A valid view token is required."})
                return
            self._json(200, snapshot)
            return
        assets = {
            "/": ("index.html", "text/html; charset=utf-8"),
            "/viewer.js": ("viewer.js", "text/javascript; charset=utf-8"),
            "/viewer.css": ("viewer.css", "text/css; charset=utf-8"),
        }
        if parsed.path not in assets or parsed.query:
            self._json(404, {"error": "Not found."})
            return
        filename, content_type = assets[parsed.path]
        try:
            body = files("arch_review").joinpath("viewer", filename).read_bytes()
        except (FileNotFoundError, OSError):
            self._json(503, {"error": "Viewer assets are not installed."})
            return
        self._respond(200, body, content_type)

    def do_HEAD(self) -> None:
        self.do_GET()

    def _method_not_allowed(self) -> None:
        self._json(405, {"error": "This viewer only accepts read-only requests."})
        self.close_connection = True

    do_POST = _method_not_allowed
    do_PUT = _method_not_allowed
    do_PATCH = _method_not_allowed
    do_DELETE = _method_not_allowed
    do_OPTIONS = _method_not_allowed


class ViewerManager:
    """Own diagrams for one assistant session, without loading the model.

    A closed browser does not stop this service or the model. Updating a diagram
    never opens a browser. Closing a view is separate from closing its window.
    """

    def __init__(self, *, max_views: int = 8):
        if isinstance(max_views, bool) or not isinstance(max_views, int) or not 1 <= max_views <= 8:
            raise ValueError("max_views must be an integer between 1 and 8.")
        self._max_views = max_views
        self._views: OrderedDict[str, _View] = OrderedDict()
        self._lock = threading.RLock()
        self._server: _ViewerHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._shutdown = False

    def _ensure_server(self) -> None:
        if self._shutdown:
            raise RuntimeError("This viewer session has shut down.")
        if self._server is None:
            self._server = _ViewerHTTPServer(self)
            self._thread = threading.Thread(
                target=self._server.serve_forever,
                kwargs={"poll_interval": 0.1},
                name="archrivet-viewer",
                daemon=True,
            )
            self._thread.start()

    @staticmethod
    def _validated(diagram: Diagram | dict[str, Any]) -> Diagram:
        # Validate and copy even an existing model: callers must not mutate state.
        return Diagram.model_validate(diagram.model_dump() if isinstance(diagram, Diagram) else diagram)

    def _snapshot(self, view: _View, *, include_url: bool = False) -> dict[str, Any]:
        snapshot = {
            "view_id": view.view_id,
            "revision": view.revision,
            "active": view.active,
            "diagram": view.diagram.model_dump(mode="json"),
            "changes": {key: list(value) for key, value in view.changes.items()},
            "updated_at": view.updated_at,
        }
        if include_url:
            assert self._server is not None
            fragment = urlencode({"view": view.view_id, "token": view.token})
            snapshot["url"] = f"http://127.0.0.1:{self._server.server_port}/#{fragment}"
        return snapshot

    def _authorized_snapshot(self, view_id: str, token: str) -> dict[str, Any] | None:
        with self._lock:
            view = self._views.get(view_id)
            if view is None or not hmac.compare_digest(token.encode("utf-8"), view.token.encode("ascii")):
                return None
            return self._snapshot(view)

    @staticmethod
    def _launch(url: str) -> bool:
        try:
            return bool(webbrowser.open(url, new=1, autoraise=True))
        except Exception:
            # A missing display/browser is normal for a headless MCP host.
            return False

    def create(self, diagram: Diagram | dict[str, Any], open_browser: bool = False) -> dict[str, Any]:
        graph = self._validated(diagram)
        with self._lock:
            if len(self._views) >= self._max_views:
                closed = next((key for key, view in self._views.items() if not view.active), None)
                if closed is None:
                    raise ViewerLimitError("Close an existing view before creating another (maximum 8 views).")
                del self._views[closed]
            self._ensure_server()
            view = _View(
                secrets.token_hex(12), secrets.token_urlsafe(32), graph, 1, True, _changes(None, graph), _timestamp()
            )
            self._views[view.view_id] = view
            snapshot = self._snapshot(view, include_url=True)
        snapshot["browser_opened"] = self._launch(snapshot["url"]) if open_browser else False
        return snapshot

    def update(
        self, view_id: str, diagram: Diagram | dict[str, Any], expected_revision: int
    ) -> dict[str, Any]:
        graph = self._validated(diagram)
        if isinstance(expected_revision, bool) or not isinstance(expected_revision, int) or expected_revision < 1:
            raise ValueError("expected_revision must be a positive integer.")
        with self._lock:
            view = self._views[view_id]
            if view.revision != expected_revision:
                raise RevisionConflict(
                    f"Expected revision {expected_revision}, but the current revision is {view.revision}. "
                    "Read the current view before updating it."
                )
            view.changes = _changes(view.diagram, graph)
            view.diagram = graph
            view.revision += 1
            view.updated_at = _timestamp()
            return self._snapshot(view)

    def get(self, view_id: str) -> dict[str, Any]:
        with self._lock:
            return self._snapshot(self._views[view_id], include_url=True)

    def close(self, view_id: str) -> dict[str, Any]:
        with self._lock:
            view = self._views[view_id]
            view.active = False
            view.updated_at = _timestamp()
            return self._snapshot(view)

    def open(self, view_id: str) -> dict[str, Any]:
        with self._lock:
            view = self._views[view_id]
            view.active = True
            view.updated_at = _timestamp()
            snapshot = self._snapshot(view, include_url=True)
        snapshot["browser_opened"] = self._launch(snapshot["url"])
        return snapshot

    def shutdown(self) -> None:
        with self._lock:
            self._shutdown = True
            server, thread = self._server, self._thread
            self._server = None
            self._thread = None
            self._views.clear()
        if server is not None:
            server.shutdown()
            server.server_close()
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2)
