// Model Flow dependency map. Its own page (not app.js) -- fetches /api/graph
// (built by "Rebuild database" / the CLI `build` command from role="input_file"/
// role="output_file" config entries, see classes/Parser.py's build_graph) and
// renders it as a single D3-rendered, dagre-laid-out layered (Sugiyama-style)
// graph: every module starts collapsed (shown as one node); clicking a
// collapsed module expands it in place into its own task nodes, without
// hiding any other module -- there is no separate "module view"/"task view"
// to navigate between, just an expanded/collapsed state per module within one
// continuous graph. Layout is computed once per render by dagre (vendored as
// /dagre.min.js); D3 only handles drawing, zoom/pan, drag, and interaction --
// there is no continuous physics simulation.

let graphData = null;
let expandedModules = new Set();
let selectedNodeId = null;
let selectedExtensions = new Set();
let currentEdges = [];
let lastLayoutSize = null;
let moduleColorScale = null;

// Modules unchecked in the "Modules" sidebar list -- excluded entirely from
// computeGraph()'s nodes/edges (not just dimmed like the extension filter),
// since a hidden node's id would otherwise still be referenced by a dagre edge.
const HIDDEN_MODULES_STORAGE_KEY = "modelflow.map.hiddenModules";
let hiddenModules = loadHiddenModules();

function loadHiddenModules() {
    try {
        return new Set(JSON.parse(localStorage.getItem(HIDDEN_MODULES_STORAGE_KEY)) || []);
    } catch (e) {
        return new Set();
    }
}

function saveHiddenModules() {
    try {
        localStorage.setItem(HIDDEN_MODULES_STORAGE_KEY, JSON.stringify([...hiddenModules]));
    } catch (e) {
        // localStorage unavailable -- persistence is a nice-to-have, not a requirement.
    }
}

// Validated categorical palette (dataviz skill, references/palette.md), fixed
// order, never cycled *within* a single 8-module view -- but a node-link graph
// is an all-pairs-visible layout (any two nodes can end up adjacent), which the
// palette itself only validates for 3 slots all-pairs, so past 8 modules the
// scale wraps. That's an acceptable secondary-encoding trade here specifically
// because every node already carries a direct text label -- identity never
// relies on color alone even when hues repeat.
const MODULE_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"];

// ---- Layout settings (controls in the "Settings" sidebar section) ----------
// Persisted the same way index.html/app.js persists its own UI state
// (localStorage, best-effort -- absent/corrupt storage just falls back to
// LAYOUT_DEFAULTS rather than breaking the page). These map directly onto
// dagre.graphlib's own graph-level layout options (rankdir/ranksep/nodesep).

const LAYOUT_STORAGE_KEY = "modelflow.map.layout";
const LAYOUT_DEFAULTS = { rankdir: "LR", ranksep: 70, nodesep: 40 };
const LAYOUT_FIELDS = [
    { id: "setting-rank-direction", key: "rankdir", type: "select" },
    { id: "setting-rank-sep", key: "ranksep", type: "range", format: (v) => v },
    { id: "setting-node-sep", key: "nodesep", type: "range", format: (v) => v },
];

function loadLayoutSettings() {
    try {
        return { ...LAYOUT_DEFAULTS, ...JSON.parse(localStorage.getItem(LAYOUT_STORAGE_KEY)) };
    } catch (e) {
        return { ...LAYOUT_DEFAULTS };
    }
}

function saveLayoutSettings() {
    try {
        localStorage.setItem(LAYOUT_STORAGE_KEY, JSON.stringify(layoutSettings));
    } catch (e) {
        // localStorage unavailable -- persistence is a nice-to-have, not a requirement.
    }
}

let layoutSettings = loadLayoutSettings();

function syncLayoutInputs() {
    for (const field of LAYOUT_FIELDS) {
        document.getElementById(field.id).value = layoutSettings[field.key];
        if (field.type === "range") {
            document.getElementById(`${field.id}-value`).textContent = field.format(layoutSettings[field.key]);
        }
    }
}

function applyLayoutSettings() {
    // Layout is one-shot (no live physics to nudge), so a settings change just
    // triggers a full recompute-and-redraw with the new dagre graph options.
    if (graphData) render();
}

for (const field of LAYOUT_FIELDS) {
    document.getElementById(field.id).addEventListener("input", (e) => {
        layoutSettings[field.key] = field.type === "range" ? parseFloat(e.target.value) : e.target.value;
        if (field.type === "range") {
            document.getElementById(`${field.id}-value`).textContent = field.format(layoutSettings[field.key]);
        }
        applyLayoutSettings();
        saveLayoutSettings();
    });
}

document.getElementById("setting-reset-btn").addEventListener("click", () => {
    layoutSettings = { ...LAYOUT_DEFAULTS };
    syncLayoutInputs();
    applyLayoutSettings();
    saveLayoutSettings();
});

syncLayoutInputs();

const svg = d3.select("#map-svg");
const zoomLayer = svg.append("g").attr("class", "zoom-layer");
const linkLayer = zoomLayer.append("g").attr("class", "link-layer");
const nodeLayer = zoomLayer.append("g").attr("class", "node-layer");

svg.append("defs").append("marker")
    .attr("id", "arrowhead")
    .attr("viewBox", "0 -5 10 10")
    .attr("refX", 22)
    .attr("refY", 0)
    .attr("markerWidth", 7)
    .attr("markerHeight", 7)
    .attr("orient", "auto")
    .append("path")
    .attr("d", "M0,-5L10,0L0,5")
    .attr("class", "map-arrow");

const zoomBehavior = d3.zoom().scaleExtent([0.2, 4]).on("zoom", (event) => {
    zoomLayer.attr("transform", event.transform);
});
svg.call(zoomBehavior);

svg.on("click", (event) => {
    if (event.target === svg.node()) {
        selectNode(null);
    }
});

function svgSize() {
    const rect = document.getElementById("map-svg-pane").getBoundingClientRect();
    return { width: rect.width, height: rect.height };
}

// ---- Data loading ----------------------------------------------------------

fetch("/api/graph")
    .then((r) => {
        if (!r.ok) throw new Error("no graph");
        return r.json();
    })
    .then((data) => {
        graphData = data;
        // Domain is every module, sorted, fixed once at load -- so a task node
        // always agrees with the color its module was shown with while collapsed.
        moduleColorScale = d3.scaleOrdinal().domain(Object.keys(graphData.modules).sort()).range(MODULE_COLORS);
        // Unlike the extension filter (rebuilt every renderGraph() call since
        // extensions vary with expand/collapse state), the module list is
        // static per graph load, so this only needs to run once here.
        renderModuleFilter();
        render();
        if (lastLayoutSize) fitToViewport(lastLayoutSize.width, lastLayoutSize.height);
    })
    .catch(() => {
        document.getElementById("map-empty-message").classList.remove("d-none");
    });

// ---- Module filter (excludes hidden modules' nodes/edges entirely) ---------

function renderModuleFilter() {
    const container = document.getElementById("map-module-filter");
    container.innerHTML = "";
    for (const moduleName of Object.keys(graphData.modules).sort()) {
        const id = `mod-${moduleName.replace(/[^a-zA-Z0-9]/g, "_")}`;
        // Checkbox itself is colored as a solid swatch of the module's graph
        // color (not just when checked) -- doubles as a legend so this list
        // is both the filter and the color key, with no separate UI needed.
        const color = moduleColorScale(moduleName);
        const wrapper = document.createElement("div");
        wrapper.className = "form-check";
        wrapper.innerHTML = `
            <input class="form-check-input" type="checkbox" id="${id}" style="background-color:${color};border-color:${color}" ${hiddenModules.has(moduleName) ? "" : "checked"}>
            <label class="form-check-label small" for="${id}">${moduleName}</label>
        `;
        wrapper.querySelector("input").addEventListener("change", (e) => {
            if (e.target.checked) hiddenModules.delete(moduleName);
            else hiddenModules.add(moduleName);
            saveHiddenModules();
            render();
        });
        container.appendChild(wrapper);
    }
}

document.getElementById("map-modules-all-link").addEventListener("click", (e) => {
    e.preventDefault();
    hiddenModules.clear();
    saveHiddenModules();
    renderModuleFilter();
    render();
});

document.getElementById("map-modules-none-link").addEventListener("click", (e) => {
    e.preventDefault();
    hiddenModules = new Set(Object.keys(graphData.modules));
    saveHiddenModules();
    renderModuleFilter();
    render();
});

// ---- Graph derivation -------------------------------------------------------
// graphData.links is the single source of truth. Every render, nodes/edges are
// rebuilt from it plus the current expandedModules set: a collapsed module is
// one node (its own name as id); an expanded module contributes one node per
// task (id "module::task", since task names aren't unique across modules). A
// link's endpoint resolves to whichever form its module is currently in -- an
// intra-module link between two collapsed-into-the-same-node endpoints becomes
// a self-loop and is dropped.

function groupLinks(rawLinks, sourceKey, targetKey) {
    const groups = new Map();
    for (const link of rawLinks) {
        const source = link[sourceKey];
        const target = link[targetKey];
        const key = `${source} ${target}`;
        if (!groups.has(key)) {
            groups.set(key, { source, target, contributions: [] });
        }
        groups.get(key).contributions.push({
            file: link.file,
            extension: link.extension,
            from_task: link.from_task,
            to_task: link.to_task,
        });
    }
    return [...groups.values()];
}

function taskNodeId(moduleName, taskName) {
    return `${moduleName}::${taskName}`;
}

function computeGraph() {
    // No position carry-over across re-renders: dagre has no warm-start, it
    // recomputes ranks/order from scratch on every layout, so a structural
    // change (expanding/collapsing a module) can legitimately shift every
    // downstream node -- seeding old x/y wouldn't be honored anyway.
    const nodes = [];
    for (const moduleName of Object.keys(graphData.modules)) {
        if (hiddenModules.has(moduleName)) continue;
        if (expandedModules.has(moduleName)) {
            for (const task of graphData.tasks[moduleName] || []) {
                nodes.push({ id: taskNodeId(moduleName, task.name), label: task.name, kind: "task", module: moduleName });
            }
        } else {
            nodes.push({ id: moduleName, label: moduleName, kind: "module", module: moduleName });
        }
    }

    const endpointId = (moduleName, taskName) =>
        expandedModules.has(moduleName) ? taskNodeId(moduleName, taskName) : moduleName;
    const rawLinks = graphData.links
        .filter((l) => !hiddenModules.has(l.from_module) && !hiddenModules.has(l.to_module))
        .map((l) => ({
            sourceId: endpointId(l.from_module, l.from_task),
            targetId: endpointId(l.to_module, l.to_task),
            file: l.file,
            extension: l.extension,
            from_task: l.from_task,
            to_task: l.to_task,
        }))
        .filter((l) => l.sourceId !== l.targetId);
    const edges = groupLinks(rawLinks, "sourceId", "targetId");

    return { nodes, edges };
}

function render() {
    const { nodes, edges } = computeGraph();
    renderGraph(nodes, edges);
    renderExpandedModulesList();
}

function expandModule(moduleName) {
    expandedModules.add(moduleName);
    render();
}

function collapseModule(moduleName) {
    expandedModules.delete(moduleName);
    selectNode(null);
    render();
}

function renderExpandedModulesList() {
    const container = document.getElementById("map-expanded-list");
    container.innerHTML = "";
    if (!expandedModules.size) {
        container.innerHTML = '<div class="text-muted small">None -- click a module node to expand it.</div>';
        return;
    }
    for (const name of [...expandedModules].sort()) {
        const chip = document.createElement("span");
        chip.className = "badge text-bg-light border me-1 mb-1 map-expanded-chip";
        chip.textContent = name + " ";
        const closeBtn = document.createElement("span");
        closeBtn.className = "map-collapse-x";
        closeBtn.textContent = "×";
        closeBtn.title = `Collapse ${name}`;
        closeBtn.addEventListener("click", () => collapseModule(name));
        chip.appendChild(closeBtn);
        container.appendChild(chip);
    }
}

document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && expandedModules.size) {
        expandedModules.clear();
        selectNode(null);
        render();
    }
});

// ---- Layout computation (dagre) ----------------------------------------------

const NODE_SHAPE = {
    module: { r: 16, dy: 30 },
    task: { r: 12, dy: 26 },
};

function measureLabelWidth(text) {
    // Cached offscreen canvas context; font must match .map-node text's CSS.
    if (!measureLabelWidth.ctx) measureLabelWidth.ctx = document.createElement("canvas").getContext("2d");
    measureLabelWidth.ctx.font = "11px sans-serif";
    return measureLabelWidth.ctx.measureText(text).width;
}

function computeDagreLayout(nodes, edges) {
    const g = new dagre.graphlib.Graph();
    g.setGraph({ rankdir: layoutSettings.rankdir, nodesep: layoutSettings.nodesep, ranksep: layoutSettings.ranksep });
    g.setDefaultEdgeLabel(() => ({}));

    for (const n of nodes) {
        const shape = NODE_SHAPE[n.kind];
        // Node box includes the label drawn *below* the circle (dy), not just
        // the circle itself -- otherwise nodesep/ranksep would let neighboring
        // labels overlap even though the circles themselves don't.
        g.setNode(n.id, { width: Math.max(shape.r * 2, measureLabelWidth(n.label) + 6), height: shape.dy + 14 });
    }
    for (const e of edges) g.setEdge(e.source, e.target);

    dagre.layout(g);
    return g;
}

// Straight segments only (default curveLinear) -- a smoothing curve wouldn't
// pass exactly through the endpoints, which would break the arrowhead
// marker's refX pullback (it assumes the final path segment ends exactly at
// the target node's center).
const edgeLineGen = d3.line().x((d) => d.x).y((d) => d.y);

function redrawEdgePath(e) {
    const source = { x: e.source.x, y: e.source.y };
    const target = { x: e.target.x, y: e.target.y };
    if (!e.points || e.points.length < 2) return edgeLineGen([source, target]);
    const points = e.points.slice();
    points[0] = source;
    points[points.length - 1] = target;
    return edgeLineGen(points);
}

function fitToViewport(graphWidth, graphHeight) {
    if (!graphWidth || !graphHeight) return;
    const { width, height } = svgSize();
    const padding = 40;
    const scale = Math.min((width - padding * 2) / graphWidth, (height - padding * 2) / graphHeight, 1.5);
    const tx = (width - graphWidth * scale) / 2;
    const ty = (height - graphHeight * scale) / 2;
    svg.transition().duration(400).call(
        zoomBehavior.transform,
        d3.zoomIdentity.translate(tx, ty).scale(Math.max(scale, 0.1))
    );
}

// ---- Rendering --------------------------------------------------------------

function renderGraph(nodes, edges) {
    // A selected task survives a re-render caused by expanding/collapsing a
    // *different* module (its detail panel and chain highlight stay put); if
    // its own module just collapsed, though, the node itself is gone.
    if (selectedNodeId && !nodes.some((n) => n.id === selectedNodeId)) {
        selectedNodeId = null;
        showEmptyDetail();
    }

    const extensions = [...new Set(edges.flatMap((e) => e.contributions.map((c) => c.extension || "(none)")))].sort();
    selectedExtensions = new Set(extensions);
    renderExtensionFilter(extensions);

    linkLayer.selectAll("*").remove();
    nodeLayer.selectAll("*").remove();

    const g = computeDagreLayout(nodes, edges);
    const nodeById = new Map(nodes.map((n) => [n.id, n]));
    for (const n of nodes) Object.assign(n, g.node(n.id));
    for (const e of edges) {
        e.source = nodeById.get(e.source);
        e.target = nodeById.get(e.target);
        e.points = g.edge(e.source.id, e.target.id).points;
    }
    currentEdges = edges;
    lastLayoutSize = { width: g.graph().width, height: g.graph().height };

    const linkSel = linkLayer.selectAll("path")
        .data(edges)
        .join("path")
        .attr("class", "map-link")
        .attr("marker-end", "url(#arrowhead)")
        .attr("d", redrawEdgePath);

    linkSel.each(function (d) {
        d3.select(this).append("title").text(
            d.contributions.map((c) => c.file).join("\n")
        );
    });

    const nodeGroup = nodeLayer.selectAll("g.map-node")
        .data(nodes, (d) => d.id)
        .join((enter) => {
            const g = enter.append("g").attr("class", (d) => `map-node map-node-${d.kind}`);
            g.append("circle")
                .attr("r", (d) => (d.kind === "module" ? 16 : 12))
                .attr("fill", (d) => moduleColorScale(d.module));
            g.append("text")
                .attr("dy", (d) => (d.kind === "module" ? 30 : 26))
                .attr("text-anchor", "middle")
                .text((d) => d.label);
            return g;
        })
        .attr("transform", (d) => `translate(${d.x},${d.y})`);

    nodeGroup.on("click", (event, d) => {
        event.stopPropagation();
        if (d.kind === "module") {
            expandModule(d.id);
        } else {
            selectNode(d);
        }
    });
    nodeGroup.call(
        d3.drag()
            .on("start", function () {
                d3.select(this).raise();
            })
            .on("drag", function (event, d) {
                d.x = event.x;
                d.y = event.y;
                d3.select(this).attr("transform", `translate(${d.x},${d.y})`);
                linkLayer.selectAll("path")
                    .filter((e) => e.source === d || e.target === d)
                    .attr("d", redrawEdgePath);
            })
    );

    applyExtensionFilter();
    applyChainHighlight();
}

// ---- Extension filter (dims edges/nodes, doesn't remove them) -------------

function renderExtensionFilter(extensions) {
    const container = document.getElementById("map-extension-filter");
    container.innerHTML = "";
    if (!extensions.length) {
        container.innerHTML = '<div class="text-muted small">No file links visible right now.</div>';
        return;
    }
    for (const ext of extensions) {
        const id = `ext-${ext.replace(/[^a-zA-Z0-9]/g, "_")}`;
        const wrapper = document.createElement("div");
        wrapper.className = "form-check";
        wrapper.innerHTML = `
            <input class="form-check-input" type="checkbox" id="${id}" checked>
            <label class="form-check-label small" for="${id}">${ext}</label>
        `;
        wrapper.querySelector("input").addEventListener("change", (e) => {
            if (e.target.checked) selectedExtensions.add(ext);
            else selectedExtensions.delete(ext);
            applyExtensionFilter();
        });
        container.appendChild(wrapper);
    }
}

function applyExtensionFilter() {
    linkLayer.selectAll("path").classed("filtered-out", (d) =>
        !d.contributions.some((c) => selectedExtensions.has(c.extension || "(none)"))
    );
}

// ---- Chain highlight (click a task -> dim everything not upstream/downstream) --

function connectedNodeIds(nodeId, edges) {
    const adjacency = new Map();
    for (const e of edges) {
        const sourceId = typeof e.source === "object" ? e.source.id : e.source;
        const targetId = typeof e.target === "object" ? e.target.id : e.target;
        if (!adjacency.has(sourceId)) adjacency.set(sourceId, []);
        if (!adjacency.has(targetId)) adjacency.set(targetId, []);
        adjacency.get(sourceId).push(targetId);
        adjacency.get(targetId).push(sourceId);
    }
    const seen = new Set([nodeId]);
    const queue = [nodeId];
    while (queue.length) {
        const current = queue.shift();
        for (const neighbor of adjacency.get(current) || []) {
            if (!seen.has(neighbor)) {
                seen.add(neighbor);
                queue.push(neighbor);
            }
        }
    }
    return seen;
}

function applyChainHighlight() {
    if (!selectedNodeId) {
        nodeLayer.selectAll("g.map-node").classed("not-in-chain", false).classed("selected", false);
        linkLayer.selectAll("path").classed("not-in-chain", false);
        return;
    }
    const chain = connectedNodeIds(selectedNodeId, currentEdges);
    nodeLayer.selectAll("g.map-node")
        .classed("not-in-chain", (d) => !chain.has(d.id))
        .classed("selected", (d) => d.id === selectedNodeId);
    linkLayer.selectAll("path").classed("not-in-chain", (d) => {
        const sourceId = typeof d.source === "object" ? d.source.id : d.source;
        const targetId = typeof d.target === "object" ? d.target.id : d.target;
        return !(chain.has(sourceId) && chain.has(targetId));
    });
}

// ---- Search -----------------------------------------------------------------

document.getElementById("map-search").addEventListener("input", (e) => {
    const query = e.target.value.trim().toLowerCase();
    const matches = [];
    nodeLayer.selectAll("g.map-node").classed("search-match", (d) => {
        const isMatch = query.length > 0 && d.label.toLowerCase().includes(query);
        if (isMatch) matches.push(d);
        return isMatch;
    });
    if (matches.length) {
        focusOn(matches[0]);
    }
});

function focusOn(node) {
    const { width, height } = svgSize();
    const scale = 1.5;
    const transform = d3.zoomIdentity
        .translate(width / 2, height / 2)
        .scale(scale)
        .translate(-node.x, -node.y);
    svg.transition().duration(400).call(zoomBehavior.transform, transform);
}

// ---- Detail panel ------------------------------------------------------------

function showEmptyDetail() {
    document.getElementById("map-detail-empty").classList.remove("d-none");
    document.getElementById("map-detail-content").classList.add("d-none");
}

function selectNode(node) {
    // Only task nodes reach here -- clicking a module node expands it in place
    // instead of selecting/showing a detail panel for it.
    selectedNodeId = node ? node.id : null;
    applyChainHighlight();

    if (!node) {
        showEmptyDetail();
        return;
    }

    document.getElementById("map-detail-empty").classList.add("d-none");
    document.getElementById("map-detail-content").classList.remove("d-none");
    document.getElementById("map-detail-title").textContent = node.label;
    showTaskDetail(node);
}

function showTaskDetail(node) {
    const descriptionEl = document.getElementById("map-detail-description");
    const descriptionToggleEl = document.getElementById("map-detail-description-toggle");
    renderDescription(descriptionEl, descriptionToggleEl, "Loading...");
    const body = document.getElementById("map-detail-body");
    body.innerHTML = "";

    fetch(`/api/task/${encodeURIComponent(node.module)}/${encodeURIComponent(node.label)}`)
        .then((r) => r.json())
        .then((data) => {
            if (selectedNodeId !== node.id) return; // user clicked elsewhere while this was loading
            renderDescription(descriptionEl, descriptionToggleEl, data.task.description);
            for (const param of data.task.config || []) {
                const row = document.createElement("div");
                row.className = "small mb-1";
                row.innerHTML = `<strong>${param.script_name || param.name}</strong> (${param.role || "parameter"}): ${param.script_value ?? ""}`;
                body.appendChild(row);
            }
        });
}

