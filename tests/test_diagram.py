from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from pydantic import ValidationError

from arch_review import diagram as diagram_module
from arch_review.diagram import Diagram, RevisionConflict, ViewerLimitError, ViewerManager


def graph():
    return {
        "title": "A payment design",
        "description": "A proposed flow, not a capacity guarantee.",
        "nodes": [
            {"id": "browser", "label": "Browser", "kind": "client"},
            {"id": "api", "label": "Payment API", "detail": "Retry handling is not specified."},
            {"id": "db", "label": "Orders", "kind": "database", "state": "existing"},
        ],
        "edges": [
            {"id": "request", "source": "browser", "target": "api", "label": "Pay"},
            {"id": "write", "source": "api", "target": "db", "label": "Store order"},
        ],
    }


@pytest.fixture
def manager():
    service = ViewerManager()
    yield service
    service.shutdown()


def connection(snapshot):
    parsed = urlsplit(snapshot["url"])
    credentials = parse_qs(parsed.fragment)
    return (
        f"{parsed.scheme}://{parsed.netloc}",
        "/api/state?view=" + credentials["view"][0],
        {"Authorization": "Bearer " + credentials["token"][0]},
    )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda data: data.update(title=""),
        lambda data: data.update(title="x" * 121),
        lambda data: data.update(description="x" * 2001),
        lambda data: data.update(nodes=[]),
        lambda data: data["nodes"].append(data["nodes"][0]),
        lambda data: data["edges"].append(data["edges"][0]),
        lambda data: data["edges"][0].update(target="missing"),
        lambda data: data["nodes"][0].update(id="../escape"),
        lambda data: data["nodes"][0].update(id="x" * 65),
        lambda data: data["nodes"][0].update(label="x" * 101),
        lambda data: data["nodes"][0].update(detail="x" * 1001),
        lambda data: data["nodes"][0].update(kind="executable"),
        lambda data: data["nodes"][0].update(state="proven"),
        lambda data: data["nodes"][0].update(html="<script>bad()</script>"),
        lambda data: data["nodes"][0].update(label=42),
        lambda data: data.update(mermaid="graph LR; a-->b"),
        lambda data: data.update(nodes=[{"id": f"node-{i}", "label": "A"} for i in range(81)], edges=[]),
        lambda data: data.update(
            edges=[{"id": f"edge-{i}", "source": "browser", "target": "api"} for i in range(161)]
        ),
    ],
)
def test_strict_graph_schema_rejects_ambiguous_or_unbounded_input(mutate):
    data = graph()
    mutate(data)
    with pytest.raises(ValidationError):
        Diagram.model_validate(data)


def test_plain_text_is_data_and_model_does_not_claim_safety():
    data = graph()
    data["nodes"][1]["label"] = "<img src=x onerror=alert(1)>"
    parsed = Diagram.model_validate(data)
    assert parsed.nodes[1].label == data["nodes"][1]["label"]
    assert parsed.nodes[1].state == "proposed"


def test_update_is_atomic_revisioned_and_reports_changes(manager, monkeypatch):
    launched = []
    monkeypatch.setattr(diagram_module.webbrowser, "open", lambda *args, **kwargs: launched.append(args) or True)
    source = Diagram.model_validate(graph())
    first = manager.create(source)
    source.nodes[0].label = "Mutated outside manager"
    first["diagram"]["nodes"][0]["label"] = "Mutated snapshot"
    assert manager.get(first["view_id"])["diagram"]["nodes"][0]["label"] == "Browser"
    after = graph()
    after["nodes"].pop(0)
    after["nodes"][0]["detail"] = "Idempotency key is stored with the order."
    after["nodes"].append({"id": "queue", "label": "Work queue", "kind": "queue"})
    after["edges"].pop(0)
    after["edges"][0]["label"] = "Unique write"
    after["edges"].append({"id": "enqueue", "source": "api", "target": "queue"})
    second = manager.update(first["view_id"], after, 1)
    assert second["revision"] == 2
    assert second["changes"] == {
        "added_nodes": ["queue"],
        "removed_nodes": ["browser"],
        "changed_nodes": ["api"],
        "added_edges": ["enqueue"],
        "removed_edges": ["request"],
        "changed_edges": ["write"],
    }
    with pytest.raises(RevisionConflict, match="current revision is 2"):
        manager.update(first["view_id"], graph(), 1)
    assert manager.get(first["view_id"])["diagram"]["edges"][0]["label"] == "Unique write"
    assert launched == []


def test_only_one_concurrent_update_wins(manager):
    initial = manager.create(graph())

    def attempt(number):
        changed = graph()
        changed["title"] = f"Change {number}"
        try:
            return manager.update(initial["view_id"], changed, 1)["revision"]
        except RevisionConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=4) as pool:
        outcomes = list(pool.map(attempt, range(4)))
    assert outcomes.count(2) == 1
    assert outcomes.count("conflict") == 3


@pytest.mark.parametrize("revision", [True, False, 1.0, "1", 0, -1])
def test_expected_revision_is_a_positive_integer(manager, revision):
    initial = manager.create(graph())
    with pytest.raises(ValueError, match="positive integer"):
        manager.update(initial["view_id"], graph(), revision)


def test_close_and_reopen_are_independent_of_diagram_updates(manager, monkeypatch):
    launches = []
    monkeypatch.setattr(diagram_module.webbrowser, "open", lambda *args, **kwargs: launches.append(args) or True)
    initial = manager.create(graph(), open_browser=True)
    assert initial["browser_opened"] is True
    closed = manager.close(initial["view_id"])
    assert closed["active"] is False
    assert closed["revision"] == 1
    assert manager.update(initial["view_id"], graph(), 1)["active"] is False
    assert len(launches) == 1
    reopened = manager.open(initial["view_id"])
    assert reopened["active"] is True
    assert reopened["revision"] == 2
    assert reopened["browser_opened"] is True
    assert len(launches) == 2
    assert initial["url"] == reopened["url"]


def test_browser_launch_failure_still_returns_a_usable_url(manager, monkeypatch):
    def unavailable(*args, **kwargs):
        raise OSError("No display")

    monkeypatch.setattr(diagram_module.webbrowser, "open", unavailable)
    created = manager.create(graph(), open_browser=True)
    assert created["browser_opened"] is False
    assert created["url"].startswith("http://127.0.0.1:")


def test_capacity_only_evicts_closed_views():
    manager = ViewerManager(max_views=2)
    try:
        first = manager.create(graph())
        second = manager.create(graph())
        with pytest.raises(ViewerLimitError):
            manager.create(graph())
        manager.close(first["view_id"])
        third = manager.create(graph())
        with pytest.raises(KeyError):
            manager.get(first["view_id"])
        assert manager.get(second["view_id"])["active"]
        assert manager.get(third["view_id"])["active"]
    finally:
        manager.shutdown()


def test_http_tokens_are_per_view_read_only_and_not_in_payload(manager):
    first = manager.create(graph())
    second = manager.create(graph())
    origin, route, headers = connection(first)
    _, other_route, other_headers = connection(second)
    with httpx.Client(base_url=origin, trust_env=False) as client:
        assert client.get(route).status_code == 401
        assert client.get(route, headers=other_headers).status_code == 401
        assert client.get(other_route, headers=headers).status_code == 401
        assert client.get("/api/state?view=unknown", headers=headers).status_code == 401
        response = client.get(route, headers=headers)
        assert response.status_code == 200
        assert response.json()["diagram"]["title"] == first["diagram"]["title"]
        assert "token" not in response.json()
        assert "url" not in response.json()
        assert headers["Authorization"][7:] not in response.text
        assert response.headers["Cache-Control"] == "no-store"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["Referrer-Policy"] == "no-referrer"
        assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
        assert "Access-Control-Allow-Origin" not in response.headers
        assert client.post(route, headers=headers, json={}).status_code == 405
        assert client.options(route, headers=headers).status_code == 405
        assert client.get(route + "&view=other", headers=headers).status_code == 400
        manager.close(first["view_id"])
        assert client.get(route, headers=headers).json()["active"] is False


@pytest.mark.parametrize(
    "extra_headers",
    [
        {"Host": "attacker.example"},
        {"Origin": "https://attacker.example"},
        {"Origin": "null"},
        {"Origin": "http://localhost:3000"},
        {"Sec-Fetch-Site": "cross-site"},
        {"Sec-Fetch-Site": "same-site"},
    ],
)
def test_http_rejects_foreign_origins_and_dns_rebinding(manager, extra_headers):
    initial = manager.create(graph())
    origin, route, headers = connection(initial)
    response = httpx.get(origin + route, headers={**headers, **extra_headers}, trust_env=False)
    assert response.status_code == 403


def test_same_origin_fetch_and_static_asset_allowlist(manager, monkeypatch, tmp_path):
    static = tmp_path / "viewer"
    static.mkdir()
    (static / "index.html").write_text("<h1>Viewer</h1>", encoding="utf-8")
    (static / "viewer.js").write_text("// viewer", encoding="utf-8")
    (static / "viewer.css").write_text("body {}", encoding="utf-8")
    monkeypatch.setattr(diagram_module, "files", lambda package: tmp_path)
    origin, route, headers = connection(manager.create(graph()))
    with httpx.Client(base_url=origin, trust_env=False) as client:
        same_origin = {**headers, "Origin": origin, "Sec-Fetch-Site": "same-origin"}
        assert client.get(route, headers=same_origin).status_code == 200
        for asset in ("/", "/viewer.js", "/viewer.css"):
            assert client.get(asset).status_code == 200
            assert client.head(asset).status_code == 200
        assert client.get("/diagram.py").status_code == 404
        assert client.get("/%2e%2e/diagram.py").status_code == 404
        assert client.get("/viewer.js?source=remote").status_code == 404


def test_viewers_do_not_share_state_or_tokens(manager):
    second_manager = ViewerManager()
    try:
        first = manager.create(graph())
        second = second_manager.create(graph())
        first_origin, route, headers = connection(first)
        second_origin, _, _ = connection(second)
        assert first_origin != second_origin
        with pytest.raises(KeyError):
            second_manager.get(first["view_id"])
        assert httpx.get(second_origin + route, headers=headers, trust_env=False).status_code == 401
    finally:
        second_manager.shutdown()


def test_shutdown_stops_listener_and_cannot_restart_session(manager):
    origin, route, headers = connection(manager.create(graph()))
    listener = manager._server
    manager.shutdown()
    assert listener.socket.fileno() == -1
    # Windows may drop the connection rather than immediately refuse it.
    with pytest.raises((httpx.ConnectError, httpx.ConnectTimeout)):
        httpx.get(origin + route, headers=headers, trust_env=False, timeout=1)
    with pytest.raises(RuntimeError, match="shut down"):
        manager.create(graph())
    manager.shutdown()  # Safe during multiple cleanup paths.
