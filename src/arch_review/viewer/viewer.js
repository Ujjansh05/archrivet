/* ArchRivet's local viewer. No external assets, model calls, or diagram telemetry. */
"use strict";
(() => {
  const SVG_NS = "http://www.w3.org/2000/svg";
  const NODE_WIDTH = 236;
  const NODE_HEIGHT = 108;
  const LAYER_GAP = 130;
  const ROW_GAP = 86;
  const params = new URLSearchParams(window.location.hash.slice(1));
  const viewId = params.get("view");
  const token = params.get("token");
  const element = (id) => document.getElementById(id);
  const graph = element("graph");
  const viewport = element("viewport");
  const stage = element("canvas-stage");
  let latest = null;
  let previousDiagram = null;
  let currentLayout = null;
  let selectedId = null;
  let closed = false;
  let unauthorized = false;
  let pollTimer = null;
  let request = null;
  let camera = { x: 0, y: 0, scale: 1 };
  let drag = null;

  function svg(tag, attributes = {}, text) {
    const item = document.createElementNS(SVG_NS, tag);
    for (const [key, value] of Object.entries(attributes)) item.setAttribute(key, String(value));
    if (text !== undefined) item.textContent = String(text);
    return item;
  }

  function textLines(value, maximumCharacters, maximumLines) {
    const words = String(value).trim().split(/\s+/);
    const lines = [];
    let line = "";
    for (const word of words) {
      if (line && (line.length + word.length + 1 > maximumCharacters)) {
        lines.push(line);
        line = "";
      }
      if (word.length > maximumCharacters) {
        if (line) { lines.push(line); line = ""; }
        for (let at = 0; at < word.length; at += maximumCharacters) lines.push(word.slice(at, at + maximumCharacters));
      } else line += (line ? " " : "") + word;
    }
    if (line) lines.push(line);
    if (lines.length > maximumLines) {
      lines.length = maximumLines;
      lines[maximumLines - 1] = lines[maximumLines - 1].slice(0, maximumCharacters - 1) + "…";
    }
    return lines;
  }

  /* Collapse strongly connected components before assigning layers, so cycles
     do not cause an endless layout pass or leave unrelated components behind. */
  function layout(diagram) {
    const positions = new Map();
    const order = new Map(diagram.nodes.map((node, index) => [node.id, index]));
    const adjacency = new Map(diagram.nodes.map((node) => [node.id, []]));
    diagram.edges.forEach((edge) => adjacency.get(edge.source).push(edge.target));
    const discovered = new Map();
    const low = new Map();
    const stack = [];
    const onStack = new Set();
    const components = [];
    let nextIndex = 0;
    function visit(id) {
      discovered.set(id, nextIndex);
      low.set(id, nextIndex++);
      stack.push(id);
      onStack.add(id);
      for (const other of adjacency.get(id)) {
        if (!discovered.has(other)) { visit(other); low.set(id, Math.min(low.get(id), low.get(other))); }
        else if (onStack.has(other)) low.set(id, Math.min(low.get(id), discovered.get(other)));
      }
      if (low.get(id) === discovered.get(id)) {
        const members = [];
        let other;
        do { other = stack.pop(); onStack.delete(other); members.push(other); } while (other !== id);
        components.push(members.sort((a, b) => order.get(a) - order.get(b)));
      }
    }
    diagram.nodes.forEach((node) => { if (!discovered.has(node.id)) visit(node.id); });
    const componentOf = new Map();
    components.forEach((members, index) => members.forEach((id) => componentOf.set(id, index)));
    const links = components.map(() => new Set());
    const indegree = components.map(() => 0);
    const ranks = components.map(() => 0);
    for (const edge of diagram.edges) {
      const from = componentOf.get(edge.source);
      const to = componentOf.get(edge.target);
      if (from !== to && !links[from].has(to)) { links[from].add(to); indegree[to] += 1; }
    }
    const queue = components.map((_, i) => i).filter((i) => indegree[i] === 0);
    for (let i = 0; i < queue.length; i++) {
      const from = queue[i];
      for (const to of links[from]) {
        ranks[to] = Math.max(ranks[to], ranks[from] + 1);
        indegree[to] -= 1;
        if (indegree[to] === 0) queue.push(to);
      }
    }
    const layers = [];
    for (const node of diagram.nodes) {
      const rank = ranks[componentOf.get(node.id)];
      if (!layers[rank]) layers[rank] = [];
      layers[rank].push(node.id);
    }
    const tallest = Math.max(1, ...layers.map((layer) => layer.length));
    const height = tallest * (NODE_HEIGHT + ROW_GAP) - ROW_GAP + 160;
    layers.forEach((members, rank) => {
      const total = members.length * (NODE_HEIGHT + ROW_GAP) - ROW_GAP;
      members.forEach((id, row) => positions.set(id, {
        x: 70 + rank * (NODE_WIDTH + LAYER_GAP),
        y: (height - total) / 2 + row * (NODE_HEIGHT + ROW_GAP),
        rank,
      }));
    });
    const hasCycles = diagram.edges.some((edge) => positions.get(edge.source).rank === positions.get(edge.target).rank);
    return { positions, width: Math.max(440, layers.length * (NODE_WIDTH + LAYER_GAP) - LAYER_GAP + 140 + (hasCycles ? 150 : 0)), height };
  }

  function changesSet(name) { return new Set(latest?.changes?.[name] || []); }

  function renderGraph(first) {
    const diagram = latest.diagram;
    const oldLayout = currentLayout;
    currentLayout = layout(diagram);
    element("nodes").replaceChildren();
    element("edges").replaceChildren();
    const addedNodes = changesSet("added_nodes");
    const changedNodes = changesSet("changed_nodes");
    const addedEdges = changesSet("added_edges");
    const changedEdges = changesSet("changed_edges");
    const laneByPair = new Map();
    const edgeLayer = element("edges");
    diagram.edges.forEach((edge) => {
      const from = currentLayout.positions.get(edge.source);
      const to = currentLayout.positions.get(edge.target);
      const pair = `${edge.source}\u0000${edge.target}`;
      const lane = laneByPair.get(pair) || 0;
      laneByPair.set(pair, lane + 1);
      const offset = (lane % 2 ? -1 : 1) * Math.ceil(lane / 2) * 21;
      const start = { x: from.x + NODE_WIDTH, y: from.y + NODE_HEIGHT / 2 + offset };
      const end = { x: to.x, y: to.y + NODE_HEIGHT / 2 + offset };
      let path;
      let labelX;
      let labelY;
      if (from.rank < to.rank) {
        const middle = (start.x + end.x) / 2;
        path = `M${start.x},${start.y} C${middle},${start.y} ${middle},${end.y} ${end.x},${end.y}`;
        labelX = middle;
        labelY = (start.y + end.y) / 2 - 12;
      } else {
        // A cycle uses the right side of its layer. Opposite directions take
        // separate lanes; self loops connect two distinct ports of the node.
        const downward = to.y > from.y;
        const laneOffset = (downward ? 0 : 28) + lane * 18;
        const outside = from.x + NODE_WIDTH + 62 + laneOffset;
        start.y = from.y + (edge.source === edge.target ? 30 : NODE_HEIGHT * (downward ? 0.7 : 0.3));
        end.x = to.x + NODE_WIDTH;
        end.y = to.y + (edge.source === edge.target ? 78 : NODE_HEIGHT * (downward ? 0.3 : 0.7));
        path = `M${start.x},${start.y} C${outside},${start.y} ${outside},${end.y} ${end.x},${end.y}`;
        labelX = outside - 8;
        labelY = (start.y + end.y) / 2 - 9;
      }
      const group = svg("g");
      group.appendChild(svg("path", { d: path, class: `graph-edge${addedEdges.has(edge.id) ? " added" : changedEdges.has(edge.id) ? " changed" : ""}` }));
      if (edge.label) {
        const label = textLines(edge.label, 26, 1)[0] || "";
        const width = Math.min(190, Math.max(35, label.length * 5.7 + 16));
        group.appendChild(svg("rect", { x: labelX - width / 2, y: labelY - 12, width, height: 20, rx: 5, class: "edge-label-bg" }));
        const labelText = svg("text", { x: labelX, y: labelY + 2, class: "edge-label" }, label);
        labelText.appendChild(svg("title", {}, edge.label));
        group.appendChild(labelText);
      }
      edgeLayer.appendChild(group);
    });
    diagram.nodes.forEach((node) => {
      const position = currentLayout.positions.get(node.id);
      const isAdded = addedNodes.has(node.id);
      const isChanged = changedNodes.has(node.id);
      const group = svg("g", {
        class: `graph-node${isAdded ? " added" : isChanged ? " changed" : ""}${node.id === selectedId ? " selected" : ""}`,
        transform: `translate(${position.x},${position.y})`, tabindex: "0", role: "button",
        "aria-label": `${node.label}, ${node.kind}, ${node.state}. Show component details.`,
        "data-node-id": node.id,
      });
      group.appendChild(svg("title", {}, `${node.label}${node.detail ? `\n${node.detail}` : ""}`));
      group.appendChild(svg("rect", { x: 0, y: 0, width: NODE_WIDTH, height: NODE_HEIGHT, rx: 11, class: "node-body" }));
      group.appendChild(svg("rect", { x: 16, y: 17, width: 5, height: 5, rx: 1, class: "node-accent" }));
      group.appendChild(svg("text", { x: 28, y: 23, class: "node-kind" }, textLines(node.kind.toUpperCase(), 24, 1)[0]));
      textLines(node.label, 26, 2).forEach((line, index) => group.appendChild(svg("text", { x: 16, y: 48 + index * 18, class: "node-label" }, line)));
      group.appendChild(svg("circle", { cx: 19, cy: 89, r: 2.5, class: "node-state-dot" }));
      group.appendChild(svg("text", { x: 27, y: 92, class: "node-state" }, node.state));
      if (isAdded || isChanged) group.appendChild(svg("text", { x: NODE_WIDTH - 17, y: 92, "text-anchor": "end", class: `node-change${isChanged && !isAdded ? " updated" : ""}` }, isAdded ? "NEW" : "UPDATED"));
      group.addEventListener("click", () => selectNode(node.id));
      group.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") { event.preventDefault(); selectNode(node.id); }
      });
      element("nodes").appendChild(group);
    });
    element("graph-title").textContent = diagram.title;
    element("graph-description").textContent = `${diagram.nodes.length} components and ${diagram.edges.length} connections. ${diagram.description || ""} Select a component to read its details.`;
    element("graph-counts").textContent = `${diagram.nodes.length} component${diagram.nodes.length === 1 ? "" : "s"} · ${diagram.edges.length} connection${diagram.edges.length === 1 ? "" : "s"}`;
    element("empty-state").hidden = diagram.nodes.length > 0;
    element("download-svg").disabled = diagram.nodes.length === 0;
    element("download-json").disabled = false;
    if (first || !diagram.nodes.some((node) => node.id === selectedId)) selectNode(null);
    else selectNode(selectedId);
    if (first || !oldLayout || oldLayout.width !== currentLayout.width || oldLayout.height !== currentLayout.height) fit();
  }

  function selectNode(id) {
    selectedId = id;
    const node = latest?.diagram.nodes.find((item) => item.id === id);
    element("selection-empty").hidden = !!node;
    element("selection-content").hidden = !node;
    element("clear-selection").hidden = !node;
    graph.querySelectorAll(".graph-node").forEach((item) => item.classList.toggle("selected", item.getAttribute("data-node-id") === id));
    if (!node) return;
    element("selection-kind").textContent = node.kind;
    element("selection-label").textContent = node.label;
    element("selection-state").textContent = node.state;
    element("selection-detail").textContent = node.detail || "No further detail has been provided for this component.";
    element("selection-id").textContent = node.id;
    const connections = element("selection-connections");
    connections.replaceChildren();
    const names = new Map(latest.diagram.nodes.map((item) => [item.id, item.label]));
    latest.diagram.edges.filter((edge) => edge.source === id || edge.target === id).forEach((edge) => {
      const outgoing = edge.source === id;
      const line = document.createElement("div");
      line.className = "connection-item";
      const direction = document.createElement("span");
      direction.className = "connection-direction";
      direction.textContent = outgoing ? "→" : "←";
      const label = document.createElement("span");
      label.textContent = `${names.get(outgoing ? edge.target : edge.source)}${edge.label ? ` · ${edge.label}` : ""}`;
      line.append(direction, label);
      connections.appendChild(line);
    });
  }

  function renderChanges() {
    const list = element("changes-list");
    list.replaceChildren();
    const nodes = new Map([...(previousDiagram?.nodes || []), ...latest.diagram.nodes].map((node) => [node.id, node.label]));
    const edges = new Map([...(previousDiagram?.edges || []), ...latest.diagram.edges].map((edge) => [edge.id, edge]));
    const categories = [
      ["added_nodes", "Added component", "+", ""], ["changed_nodes", "Updated component", "~", "updated"], ["removed_nodes", "Removed component", "−", "removed"],
      ["added_edges", "Added connection", "+", ""], ["changed_edges", "Updated connection", "~", "updated"], ["removed_edges", "Removed connection", "−", "removed"],
    ];
    let count = 0;
    for (const [key, title, symbol, className] of categories) {
      for (const id of latest.changes?.[key] || []) {
        count += 1;
        const item = document.createElement("li");
        item.className = "change-item";
        const icon = document.createElement("span");
        icon.className = `change-symbol ${className}`;
        icon.textContent = symbol;
        const content = document.createElement("div");
        const edge = edges.get(id);
        const label = key.endsWith("nodes") ? (nodes.get(id) || id) : edge ? `${nodes.get(edge.source) || edge.source} → ${nodes.get(edge.target) || edge.target}` : id;
        content.textContent = label;
        const subtitle = document.createElement("small");
        subtitle.textContent = title;
        content.appendChild(subtitle);
        item.append(icon, content);
        list.appendChild(item);
      }
    }
    element("change-count").textContent = String(count);
    element("changes-empty").hidden = count > 0;
    if (!count && latest.revision > 0) element("changes-empty").textContent = "No component or connection changes in this revision.";
  }

  function applyCamera() {
    viewport.setAttribute("transform", `translate(${camera.x},${camera.y}) scale(${camera.scale})`);
    element("zoom-label").textContent = `${Math.round(camera.scale * 100)}%`;
  }

  function fit() {
    if (!currentLayout) return;
    const width = stage.clientWidth;
    const height = stage.clientHeight;
    camera.scale = Math.max(0.005, Math.min(1.1, (width - 28) / currentLayout.width, (height - 28) / currentLayout.height));
    camera.x = (width - currentLayout.width * camera.scale) / 2;
    camera.y = (height - currentLayout.height * camera.scale) / 2;
    applyCamera();
  }

  function zoom(factor, centerX = stage.clientWidth / 2, centerY = stage.clientHeight / 2) {
    const next = Math.max(0.005, Math.min(2.5, camera.scale * factor));
    const change = next / camera.scale;
    camera.x = centerX - (centerX - camera.x) * change;
    camera.y = centerY - (centerY - camera.y) * change;
    camera.scale = next;
    applyCamera();
  }

  function connection(label, state = "") {
    element("connection-label").textContent = label;
    element("connection-dot").className = `connection-dot ${state}`;
  }

  function stopPolling() {
    clearTimeout(pollTimer);
    pollTimer = null;
    if (request) request.abort();
  }

  function refreshVisibility(active = true) {
    const isClosed = closed || !active;
    element("closed-state").hidden = !isClosed;
    element("closed-title").textContent = closed ? "View closed" : "Closed by the assistant";
    element("closed-message").textContent = closed
      ? "The diagram is paused. Your assistant and architecture reviews can keep working."
      : "Ask your assistant to reopen the architecture view. Your reviews can keep working.";
    element("reopen-view").hidden = !closed;
    element("close-view").textContent = closed ? "Reopen view" : "Close view";
    graph.classList.toggle("is-hidden", isClosed);
    graph.setAttribute("aria-hidden", String(isClosed));
    if (isClosed) element("empty-state").hidden = true;
    else element("empty-state").hidden = !!latest?.diagram.nodes.length;
  }

  function toggleClosed() {
    closed = !closed;
    if (closed) {
      stopPolling();
      element("offline-banner").hidden = true;
      connection("View paused", "offline");
    } else if (!unauthorized) {
      connection("Reconnecting…", "waiting");
      poll();
    }
    refreshVisibility(latest?.active !== false);
  }

  function validState(state) {
    if (!state || state.view_id !== viewId || !Number.isSafeInteger(state.revision) || state.revision < 0 || typeof state.active !== "boolean") return false;
    const diagram = state.diagram;
    if (!diagram || typeof diagram.title !== "string" || !Array.isArray(diagram.nodes) || !Array.isArray(diagram.edges) || diagram.nodes.length > 80 || diagram.edges.length > 160) return false;
    const ids = new Set();
    for (const node of diagram.nodes) {
      if (!node || ["id", "label", "kind", "state"].some((key) => typeof node[key] !== "string") || ids.has(node.id)) return false;
      ids.add(node.id);
    }
    const edgeIds = new Set();
    for (const edge of diagram.edges) {
      if (!edge || typeof edge.id !== "string" || !ids.has(edge.source) || !ids.has(edge.target) || edgeIds.has(edge.id)) return false;
      edgeIds.add(edge.id);
    }
    return true;
  }

  async function poll() {
    if (closed || unauthorized || document.hidden || request || !viewId || !token) return;
    clearTimeout(pollTimer);
    const controller = new AbortController();
    request = controller;
    const timeout = setTimeout(() => controller.abort(), 5000);
    try {
      const response = await fetch(`/api/state?view=${encodeURIComponent(viewId)}`, {
        headers: { Authorization: `Bearer ${token}` }, signal: controller.signal, cache: "no-store", credentials: "omit", redirect: "error", referrerPolicy: "no-referrer",
      });
      if (response.status === 401 || response.status === 403) {
        unauthorized = true;
        throw new Error("authorization");
      }
      if (!response.ok) throw new Error("unavailable");
      const state = await response.json();
      if (!validState(state)) throw new Error("invalid state");
      if (closed || document.hidden) return;
      element("offline-banner").hidden = true;
      connection(state.active ? "Live · connected locally" : "Waiting for the assistant", state.active ? "" : "waiting");
      if (!latest || state.revision !== latest.revision) {
        const first = !latest || !latest.diagram.nodes.length;
        previousDiagram = latest?.diagram || null;
        latest = state;
        element("design-title").textContent = state.diagram.title;
        element("design-description").textContent = state.diagram.description || "Explore the components and connections in this design.";
        element("revision-value").textContent = String(state.revision);
        const date = new Date(state.updated_at);
        element("updated-at").textContent = Number.isNaN(date.getTime()) ? "Received just now" : `Updated ${date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
        document.title = `${state.diagram.title} · ArchRivet`;
        renderGraph(first);
        renderChanges();
      } else latest.active = state.active;
      refreshVisibility(state.active);
    } catch (error) {
      if (closed || document.hidden) return;
      connection(unauthorized ? "Connection expired" : "Reconnecting…", "offline");
      element("offline-banner").textContent = unauthorized
        ? "This connection has expired. Ask your assistant to open the architecture view again."
        : latest ? "Connection lost. Showing the last received design; retrying automatically." : "Waiting for the local viewer service. Retrying automatically.";
      element("offline-banner").hidden = false;
    } finally {
      clearTimeout(timeout);
      request = null;
      if (!closed && !unauthorized && !document.hidden) pollTimer = setTimeout(poll, 1000);
    }
  }

  function saveFile(contents, type, suffix) {
    const name = (latest.diagram.title || "architecture").replace(/[^a-z0-9_-]+/gi, "-").slice(0, 70) || "architecture";
    const url = URL.createObjectURL(new Blob([contents], { type }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `${name}-r${latest.revision}.${suffix}`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function saveSvg() {
    if (!latest || !currentLayout) return;
    const copy = graph.cloneNode(true);
    copy.removeAttribute("id");
    copy.removeAttribute("tabindex");
    copy.removeAttribute("class");
    copy.removeAttribute("aria-hidden");
    copy.setAttribute("xmlns", SVG_NS);
    copy.setAttribute("viewBox", `0 0 ${currentLayout.width} ${currentLayout.height}`);
    copy.setAttribute("width", currentLayout.width);
    copy.setAttribute("height", currentLayout.height);
    copy.querySelector("#viewport").removeAttribute("transform");
    copy.querySelectorAll("[tabindex]").forEach((item) => { item.removeAttribute("tabindex"); item.removeAttribute("role"); });
    const background = svg("rect", { width: "100%", height: "100%", fill: "#101b29" });
    copy.insertBefore(background, copy.firstChild);
    const styles = svg("style", {}, ".graph-edge{fill:none;stroke:#6a879e;stroke-width:1.7;marker-end:url(#arrow)}#arrow path{fill:#8aa6b9}.graph-edge.added{stroke:#69dfc2}.graph-edge.changed{stroke:#f5c376}.edge-label-bg{fill:#101b29;stroke:#283d50;stroke-width:.7}.edge-label{fill:#b2c6d5;font:10px 'Segoe UI',sans-serif;text-anchor:middle}.node-body{fill:#172839;stroke:#385168;stroke-width:1.2}.added .node-body{stroke:#69bfae;stroke-dasharray:5 3}.changed .node-body{stroke:#c8a367}.node-accent{fill:#31556a}.node-kind{fill:#8cafc2;font:9px 'Segoe UI',sans-serif;letter-spacing:1.1px}.node-label{fill:#eef5fc;font:600 14px 'Segoe UI',sans-serif}.node-state{fill:#91a9bc;font:9px 'Segoe UI',sans-serif}.node-state-dot{fill:#7790a2}.node-change{fill:#69dfc2;font:8px 'Segoe UI',sans-serif}.node-change.updated{fill:#f5c376}");
    copy.insertBefore(styles, copy.firstChild);
    saveFile(new XMLSerializer().serializeToString(copy), "image/svg+xml", "svg");
  }

  element("brand-link").addEventListener("click", (event) => { event.preventDefault(); fit(); });
  element("close-view").addEventListener("click", toggleClosed);
  element("reopen-view").addEventListener("click", toggleClosed);
  element("clear-selection").addEventListener("click", () => selectNode(null));
  element("fit-view").addEventListener("click", fit);
  element("zoom-in").addEventListener("click", () => zoom(1.2));
  element("zoom-out").addEventListener("click", () => zoom(1 / 1.2));
  element("download-json").addEventListener("click", () => {
    if (latest) saveFile(JSON.stringify({ revision: latest.revision, diagram: latest.diagram, changes: latest.changes, updated_at: latest.updated_at }, null, 2), "application/json", "json");
  });
  element("download-svg").addEventListener("click", saveSvg);
  graph.addEventListener("wheel", (event) => {
    event.preventDefault();
    const bounds = graph.getBoundingClientRect();
    zoom(Math.exp(-Math.max(-100, Math.min(100, event.deltaY)) * 0.002), event.clientX - bounds.left, event.clientY - bounds.top);
  }, { passive: false });
  graph.addEventListener("pointerdown", (event) => {
    if (event.button !== 0 || event.target.closest(".graph-node")) return;
    drag = { x: event.clientX, y: event.clientY, cameraX: camera.x, cameraY: camera.y };
    graph.setPointerCapture(event.pointerId);
    graph.classList.add("dragging");
  });
  graph.addEventListener("pointermove", (event) => {
    if (!drag) return;
    camera.x = drag.cameraX + event.clientX - drag.x;
    camera.y = drag.cameraY + event.clientY - drag.y;
    applyCamera();
  });
  function endDrag() { drag = null; graph.classList.remove("dragging"); }
  graph.addEventListener("pointerup", endDrag);
  graph.addEventListener("pointercancel", endDrag);
  graph.addEventListener("lostpointercapture", endDrag);
  graph.addEventListener("keydown", (event) => {
    if (event.target !== graph) return;
    if (event.key === "+" || event.key === "=") { event.preventDefault(); zoom(1.2); }
    else if (event.key === "-") { event.preventDefault(); zoom(1 / 1.2); }
    else if (event.key === "0") { event.preventDefault(); fit(); }
    else if (event.key === "Escape") selectNode(null);
  });
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) stopPolling();
    else if (!closed && !unauthorized) poll();
  });
  window.addEventListener("pagehide", stopPolling);
  window.addEventListener("pageshow", () => { if (!closed && !unauthorized) poll(); });
  let resizeTimer;
  new ResizeObserver(() => { clearTimeout(resizeTimer); resizeTimer = setTimeout(fit, 120); }).observe(stage);

  if (!viewId || !token) {
    connection("No view connected", "offline");
    element("empty-state").querySelector("h2").textContent = "Open this view from your assistant";
    element("empty-state").querySelector("p").textContent = "Ask your assistant to show its system design with ArchRivet. The link it provides will connect this canvas to that design.";
  } else poll();
})();
