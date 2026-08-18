// Model Flow web GUI client. Plain vanilla JS, no build step: fetches JSON
// from /api/*, renders the module/task/pipeline tree and a config-edit form,
// and streams a run's output over a WebSocket that reconnects (with capped
// backoff) and catches up on missed events if the connection drops.

const MAX_RECONNECT_ATTEMPTS = 5;
const RECONNECT_BASE_DELAY_MS = 1000;
const UI_STATE_KEY = "modelflow.ui";

let treeData = [];
let selection = null; // {kind: "task"|"pipeline", module, name}
// Set of module-tree node paths (e.g. "v.main2020/d.policy") the user has
// collapsed. `loadUiState` is defined further down, but function
// declarations are hoisted, so calling it here at module-eval time is safe.
// Undefined (rather than []) means "never saved" -- distinguished from an
// empty array (user explicitly expanded everything) so loadTree() knows
// whether to apply the "start fully collapsed" first-visit default below.
const savedCollapsedTreePaths = loadUiState().collapsedTreePaths;
let collapsedTreePaths = new Set(savedCollapsedTreePaths || []);
let collapsedTreePathsInitialized = Array.isArray(savedCollapsedTreePaths);
let taskDefaults = {}; // script_name -> default value, for the selected task
let pipelineRows = []; // [{taskName, scriptName, inputId, defaultValue}], for the selected pipeline

let ws = null;
let eventsSeen = 0;
let reconnectAttempts = 0;
let runTerminal = false; // true once a "done"/"error" event has been received for the current run
let currentRunLabel = "";
let currentRunId = null;

function sanitizeId(value) {
    return String(value).replace(/[^a-zA-Z0-9_-]/g, "_");
}

// ---- Persisted UI state (layout sizes + last selection) -------------------
// A page refresh should land back where the user left off rather than on a
// blank "select a task" screen with default-sized panels.

function loadUiState() {
    try {
        return JSON.parse(localStorage.getItem(UI_STATE_KEY)) || {};
    } catch (e) {
        return {};
    }
}

function saveUiState(patch) {
    try {
        localStorage.setItem(UI_STATE_KEY, JSON.stringify({ ...loadUiState(), ...patch }));
    } catch (e) {
        // localStorage unavailable (e.g. some private-browsing modes) -- persistence is a
        // nice-to-have here, not a requirement, so just skip it rather than breaking the run.
    }
}

function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
}

// ---- Resizable panels -------------------------------------------------

function applySavedLayout() {
    const { treeWidth, outputHeight } = loadUiState();
    if (treeWidth) {
        document.getElementById("tree-pane").style.width = `${treeWidth}px`;
    }
    if (outputHeight) {
        applyOutputHeight(outputHeight);
    }
}

function applyOutputHeight(height) {
    // #output-body (log + any download links) tracks #output-pane's height, minus
    // the status row/padding "chrome" above it -- kept as one offset constant rather
    // than measuring, since that chrome's height doesn't change at runtime. The log
    // and downloads list split #output-body's height between themselves via flexbox.
    const HEADER_CHROME = 60;
    document.getElementById("output-pane").style.height = `${height}px`;
    document.getElementById("output-body").style.height = `${height - HEADER_CHROME}px`;
}

function setupTreeResize() {
    const handle = document.getElementById("tree-resize-handle");
    const treePane = document.getElementById("tree-pane");

    handle.addEventListener("mousedown", (e) => {
        e.preventDefault();
        handle.classList.add("resizing");
        const startX = e.clientX;
        const startWidth = treePane.getBoundingClientRect().width;
        let finalWidth = startWidth;

        function onMouseMove(moveEvent) {
            finalWidth = clamp(startWidth + (moveEvent.clientX - startX), 180, 600);
            treePane.style.width = `${finalWidth}px`;
        }

        function onMouseUp() {
            handle.classList.remove("resizing");
            document.removeEventListener("mousemove", onMouseMove);
            document.removeEventListener("mouseup", onMouseUp);
            saveUiState({ treeWidth: finalWidth });
        }

        document.addEventListener("mousemove", onMouseMove);
        document.addEventListener("mouseup", onMouseUp);
    });
}

function setupOutputResize() {
    const handle = document.getElementById("output-resize-handle");
    const outputPane = document.getElementById("output-pane");

    handle.addEventListener("mousedown", (e) => {
        e.preventDefault();
        handle.classList.add("resizing");
        const startY = e.clientY;
        const startHeight = outputPane.getBoundingClientRect().height;
        let finalHeight = startHeight;

        function onMouseMove(moveEvent) {
            // The handle sits above the output pane, so dragging up (mouse Y decreases)
            // should grow it -- hence startY - moveEvent.clientY rather than the reverse.
            const maxHeight = window.innerHeight * 0.6;
            finalHeight = clamp(startHeight + (startY - moveEvent.clientY), 120, maxHeight);
            applyOutputHeight(finalHeight);
        }

        function onMouseUp() {
            handle.classList.remove("resizing");
            document.removeEventListener("mousemove", onMouseMove);
            document.removeEventListener("mouseup", onMouseUp);
            saveUiState({ outputHeight: finalHeight });
        }

        document.addEventListener("mousemove", onMouseMove);
        document.addEventListener("mouseup", onMouseUp);
    });
}

// ---- Project title ---------------------------------------------------

function loadProjectTitle() {
    fetch("/api/config")
        .then((r) => r.json())
        .then((data) => {
            if (data.project_title) {
                document.getElementById("project-title").textContent = `— ${data.project_title}`;
                document.title = `Model Flow - ${data.project_title}`;
            }
        });
}

// ---- Tree ----------------------------------------------------------------

function loadTree() {
    fetch("/api/tree")
        .then((r) => r.json())
        .then((data) => {
            treeData = data;
            // First visit ever (nothing collapsed/expanded saved yet): start
            // fully collapsed rather than dumping every module's full task
            // list on screen at once. Later visits, and later tree reloads
            // within this session (e.g. after "Rebuild database"), respect
            // whatever the user last set instead of re-collapsing everything.
            if (!collapsedTreePathsInitialized) {
                collapsedTreePaths = allModuleTreePaths(treeData);
                collapsedTreePathsInitialized = true;
            }
            renderTree(document.getElementById("search-input").value);
            restoreSavedSelection();
        });
}

function restoreSavedSelection() {
    const { selection: saved } = loadUiState();
    if (!saved) return;
    // Look the button up by data attributes rather than re-selecting directly --
    // a module/task deleted since the last visit (e.g. after a rebuild) just won't
    // be found here, so it's silently skipped instead of erroring.
    for (const btn of document.querySelectorAll("#tree-container .tree-item")) {
        if (btn.dataset.kind === saved.kind && btn.dataset.module === saved.module && btn.dataset.name === saved.name) {
            btn.click();
            return;
        }
    }
}

// A module name is a flat string that may use "/" as a separator to express
// nested modules (e.g. "v.main2020/d.policy" -- see CLAUDE.md's Terminology
// section). The database/API treat it as one opaque string throughout; this
// splits it back apart purely for display, into a tree of {path, segment,
// children, entry} nodes -- entry is the original {module, tasks, pipelines}
// API object, attached at the node whose path exactly matches entry.module.
function buildModuleTree(entries) {
    const root = { path: "", children: {}, entry: null };
    for (const entry of entries) {
        let node = root;
        let pathSoFar = "";
        for (const segment of entry.module.split("/")) {
            pathSoFar = pathSoFar ? `${pathSoFar}/${segment}` : segment;
            if (!node.children[segment]) {
                node.children[segment] = { path: pathSoFar, segment, children: {}, entry: null };
            }
            node = node.children[segment];
        }
        node.entry = entry;
    }
    return root;
}

function renderTree(query) {
    query = (query || "").trim().toLowerCase();
    const container = document.getElementById("tree-container");
    container.innerHTML = "";

    const root = buildModuleTree(treeData);
    for (const segment of Object.keys(root.children).sort()) {
        renderModuleNode(container, root.children[segment], query, 0);
    }
}

function toggleTreeNode(path) {
    if (collapsedTreePaths.has(path)) {
        collapsedTreePaths.delete(path);
    } else {
        collapsedTreePaths.add(path);
    }
    saveUiState({ collapsedTreePaths: [...collapsedTreePaths] });
    renderTree(document.getElementById("search-input").value);
}

// Every group-node path that exists in the tree, i.e. every path a header
// could be rendered for -- used by collapseAllTreeNodes() and the "start
// fully collapsed on first visit" default in loadTree().
function allModuleTreePaths(entries) {
    const paths = new Set();
    const walk = (node) => {
        for (const child of Object.values(node.children)) {
            paths.add(child.path);
            walk(child);
        }
    };
    walk(buildModuleTree(entries));
    return paths;
}

function collapseAllTreeNodes() {
    collapsedTreePaths = allModuleTreePaths(treeData);
    saveUiState({ collapsedTreePaths: [...collapsedTreePaths] });
    renderTree(document.getElementById("search-input").value);
}

function expandAllTreeNodes() {
    collapsedTreePaths = new Set();
    saveUiState({ collapsedTreePaths: [...collapsedTreePaths] });
    renderTree(document.getElementById("search-input").value);
}

document.getElementById("collapse-all-link").addEventListener("click", (e) => {
    e.preventDefault();
    collapseAllTreeNodes();
});

document.getElementById("expand-all-link").addEventListener("click", (e) => {
    e.preventDefault();
    expandAllTreeNodes();
});

// Renders one module-path segment (and its Tasks/Pipelines, and its nested
// submodules) into `container`, applying the same match semantics as the old
// flat renderTree: a node's own path substring-matching the query reveals all
// of its tasks/pipelines *and* its entire subtree unfiltered (query reset to
// "" for the recursive call below); otherwise tasks/pipelines are filtered
// individually and a branch with no match anywhere in it is dropped entirely.
// Returns true if anything was actually appended, so an ancestor can tell
// whether to keep its own header.
//
// Collapsing (via `collapsedTreePaths`) only applies while browsing the
// unfiltered tree (query === "") -- an active search always shows matching
// branches fully expanded, same as before this feature existed, regardless
// of what's manually collapsed; toggling a header mid-search still updates
// the persisted state, it just has no visible effect until the search is
// cleared.
function renderModuleNode(container, node, query, depth) {
    const pathMatches = query === "" || node.path.toLowerCase().includes(query);
    const entry = node.entry;
    const matchingTasks = entry ? (pathMatches ? entry.tasks : entry.tasks.filter((t) => t.toLowerCase().includes(query))) : [];
    const matchingPipelines = entry
        ? (pathMatches ? entry.pipelines : entry.pipelines.filter((p) => p.toLowerCase().includes(query)))
        : [];
    const isCollapsed = query === "" && collapsedTreePaths.has(node.path);

    const fragment = document.createDocumentFragment();

    const header = document.createElement("div");
    header.className = "tree-module";
    header.style.setProperty("--depth", depth);

    const toggle = document.createElement("span");
    toggle.className = "tree-toggle";
    toggle.textContent = isCollapsed ? "▸" : "▾";
    header.appendChild(toggle);

    const label = document.createElement("span");
    label.textContent = node.segment;
    header.appendChild(label);

    header.addEventListener("click", () => toggleTreeNode(node.path));
    fragment.appendChild(header);

    if (isCollapsed) {
        container.appendChild(fragment);
        return true;
    }

    if (matchingTasks.length) {
        const tasksLabel = document.createElement("div");
        tasksLabel.className = "tree-group";
        tasksLabel.style.setProperty("--depth", depth);
        tasksLabel.textContent = "Tasks";
        fragment.appendChild(tasksLabel);
        for (const taskName of matchingTasks) {
            fragment.appendChild(makeTreeItem(entry.module, taskName, "task", depth));
        }
    }

    if (matchingPipelines.length) {
        const pipelinesLabel = document.createElement("div");
        pipelinesLabel.className = "tree-group";
        pipelinesLabel.style.setProperty("--depth", depth);
        pipelinesLabel.textContent = "Pipelines";
        fragment.appendChild(pipelinesLabel);
        for (const pipelineName of matchingPipelines) {
            fragment.appendChild(makeTreeItem(entry.module, pipelineName, "pipeline", depth));
        }
    }

    let anyChildRendered = false;
    for (const segment of Object.keys(node.children).sort()) {
        if (renderModuleNode(fragment, node.children[segment], pathMatches ? "" : query, depth + 1)) {
            anyChildRendered = true;
        }
    }

    const ownMatch = matchingTasks.length > 0 || matchingPipelines.length > 0;
    if (!ownMatch && !anyChildRendered && !pathMatches) {
        return false;
    }
    container.appendChild(fragment);
    return true;
}

function makeTreeItem(module, name, kind, depth) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "tree-item";
    btn.style.setProperty("--depth", depth);
    btn.textContent = name;
    btn.dataset.module = module;
    btn.dataset.name = name;
    btn.dataset.kind = kind;
    btn.addEventListener("click", () => {
        document.querySelectorAll("#tree-container .tree-item.active").forEach((el) => el.classList.remove("active"));
        btn.classList.add("active");
        saveUiState({ selection: { kind, module, name } });
        if (kind === "task") {
            selectTask(module, name);
        } else {
            selectPipeline(module, name);
        }
    });
    return btn;
}

document.getElementById("search-input").addEventListener("input", (e) => renderTree(e.target.value));

// ---- Detail / form ---------------------------------------------------------

function showDetail() {
    document.getElementById("detail-empty").classList.add("d-none");
    document.getElementById("detail-content").classList.remove("d-none");
}

function paramRow(labelText, inputId, value, historyValues) {
    const row = document.createElement("div");
    row.className = "param-row";

    const label = document.createElement("div");
    label.className = "param-label";
    label.textContent = labelText;
    row.appendChild(label);

    const input = document.createElement("input");
    input.type = "text";
    input.className = "form-control form-control-sm param-input";
    input.id = inputId;
    input.value = value;
    row.appendChild(input);

    if (historyValues && historyValues.length) {
        const select = document.createElement("select");
        select.className = "form-select form-select-sm param-history";
        const placeholder = document.createElement("option");
        placeholder.textContent = "History";
        placeholder.value = "";
        placeholder.selected = true;
        select.appendChild(placeholder);
        for (const v of [...historyValues].reverse()) {
            const opt = document.createElement("option");
            opt.value = v;
            opt.textContent = v;
            select.appendChild(opt);
        }
        select.addEventListener("change", () => {
            if (select.value !== "") {
                input.value = select.value;
            }
        });
        row.appendChild(select);
    }

    return row;
}

function selectTask(module, taskName) {
    fetch(`/api/task/${encodeURIComponent(module)}/${encodeURIComponent(taskName)}`)
        .then((r) => r.json())
        .then((data) => {
            selection = { kind: "task", module, name: taskName };
            taskDefaults = {};
            pipelineRows = [];

            showDetail();
            document.getElementById("detail-title").textContent = `${module}/${taskName}`;
            renderDescription(
                document.getElementById("detail-description"),
                document.getElementById("detail-description-toggle"),
                data.task.description
            );

            const form = document.getElementById("detail-form");
            form.innerHTML = "";
            for (const param of data.task.config || []) {
                if (!param.script_name) continue;
                const value = String(param.script_value ?? "");
                taskDefaults[param.script_name] = value;
                const inputId = `input-${sanitizeId(param.script_name)}`;
                const history = (data.history || {})[param.script_name];
                form.appendChild(paramRow(`${param.script_name} (${param.role || "parameter"})`, inputId, value, history));
            }

            document.getElementById("run-btn").onclick = () => runTask(module, taskName);
        });
}

function selectPipeline(module, pipelineName) {
    fetch(`/api/pipeline/${encodeURIComponent(module)}/${encodeURIComponent(pipelineName)}`)
        .then((r) => r.json())
        .then((data) => {
            selection = { kind: "pipeline", module, name: pipelineName };
            taskDefaults = {};
            pipelineRows = [];

            showDetail();
            document.getElementById("detail-title").textContent = `${module}/${pipelineName} (pipeline)`;
            renderDescription(
                document.getElementById("detail-description"),
                document.getElementById("detail-description-toggle"),
                data.pipeline.description
            );

            const form = document.getElementById("detail-form");
            form.innerHTML = "";

            for (const taskEntry of data.tasks) {
                const header = document.createElement("div");
                header.className = "pipeline-task-header";
                header.textContent = taskEntry.task_name;
                form.appendChild(header);

                if (taskEntry.loop) {
                    const summary = document.createElement("div");
                    summary.className = "text-muted";
                    summary.textContent = taskEntry.loop_summary;
                    form.appendChild(summary);
                    continue;
                }

                for (const param of taskEntry.config || []) {
                    if (!param.script_name) continue;
                    const defaultValue = String(
                        (taskEntry.overrides || {})[param.script_name] ?? param.script_value ?? ""
                    );
                    const inputId = `input-pipeline-${sanitizeId(taskEntry.task_name)}-${sanitizeId(param.script_name)}`;
                    pipelineRows.push({
                        taskName: taskEntry.task_name,
                        scriptName: param.script_name,
                        inputId,
                        defaultValue,
                    });
                    const history = (taskEntry.history || {})[param.script_name];
                    form.appendChild(
                        paramRow(`${param.script_name} (${param.role || "parameter"})`, inputId, defaultValue, history)
                    );
                }
            }

            document.getElementById("run-btn").onclick = () => runPipeline(module, pipelineName);
        });
}

function getTaskOverrides() {
    const overrides = {};
    for (const [scriptName, defaultValue] of Object.entries(taskDefaults)) {
        const input = document.getElementById(`input-${sanitizeId(scriptName)}`);
        if (input && input.value !== defaultValue) {
            overrides[scriptName] = input.value;
        }
    }
    return overrides;
}

function getPipelineOverrides() {
    const overrides = {};
    for (const row of pipelineRows) {
        const input = document.getElementById(row.inputId);
        if (input && input.value !== row.defaultValue) {
            overrides[row.taskName] = overrides[row.taskName] || {};
            overrides[row.taskName][row.scriptName] = input.value;
        }
    }
    return overrides;
}

// ---- Run / rebuild / kill --------------------------------------------------

function setRunningUiState(running) {
    document.getElementById("run-btn").disabled = running;
    document.getElementById("rebuild-btn").disabled = running;
    document.getElementById("kill-btn").disabled = !running;
}

function startRun(fetchPromise, label) {
    fetchPromise
        .then((r) => r.json().then((body) => ({ ok: r.ok, body })))
        .then(({ ok, body }) => {
            if (!ok) {
                setStatus(body.error || "Failed to start run");
                return;
            }
            currentRunLabel = label;
            currentRunId = body.run_id;
            document.getElementById("output-log").textContent = "";
            clearRunOutputs();
            setStatus(`Running ${label}... `);
            setRunningUiState(true);
            setWsIndicator("connecting");
            eventsSeen = 0;
            reconnectAttempts = 0;
            runTerminal = false;
            connectWebSocket(body.run_id, 0);
        });
}

function runTask(module, taskName) {
    startRun(
        fetch("/api/run_task", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ module, task: taskName, overrides: getTaskOverrides() }),
        }),
        `${module}/${taskName}`
    );
}

function runPipeline(module, pipelineName) {
    startRun(
        fetch("/api/run_pipeline", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ module, pipeline: pipelineName, overrides: getPipelineOverrides() }),
        }),
        `${module}/${pipelineName} (pipeline)`
    );
}

document.getElementById("rebuild-btn").addEventListener("click", () => {
    startRun(fetch("/api/rebuild", { method: "POST" }), "database rebuild");
});

document.getElementById("map-btn").addEventListener("click", () => {
    window.open("/map.html", "_blank");
});

document.getElementById("clear-btn").addEventListener("click", () => {
    document.getElementById("output-log").textContent = "";
    clearRunOutputs();
    setStatus("Select a task, then press Run.");
    setWsIndicator("idle");
});

document.getElementById("kill-btn").addEventListener("click", () => {
    fetch("/api/kill", { method: "POST" }).then((r) =>
        r.json().then((body) => {
            if (!r.ok) setStatus(body.error || "Failed to kill run");
        })
    );
});

function setStatus(message) {
    document.getElementById("status-line").textContent = message;
}

function appendLog(line) {
    const log = document.getElementById("output-log");
    log.textContent += line + "\n";
    log.scrollTop = log.scrollHeight;
}

// ---- WebSocket connection indicator ----------------------------------------
// Renders connectWebSocket's existing connecting/live/reconnecting/gave-up
// states as a glanceable badge, instead of only being visible indirectly
// through the status-line text.

const WS_INDICATOR_STATES = {
    connecting: { text: "Connecting…", cls: "text-bg-warning" },
    live: { text: "Live", cls: "text-bg-success" },
    reconnecting: () => ({ text: `Reconnecting… (${reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS})`, cls: "text-bg-warning" }),
    disconnected: { text: "Disconnected", cls: "text-bg-danger" },
};

function setWsIndicator(state) {
    const el = document.getElementById("ws-indicator");
    const entry = WS_INDICATOR_STATES[state];
    if (!entry) {
        el.className = "badge d-none";
        el.textContent = "";
        return;
    }
    const { text, cls } = typeof entry === "function" ? entry() : entry;
    el.className = `badge ${cls}`;
    el.textContent = text;
}

// ---- WebSocket streaming with reconnect-and-catch-up -----------------------

function connectWebSocket(runId, fromIndex) {
    const protocol = location.protocol === "https:" ? "wss:" : "ws:";
    ws = new WebSocket(`${protocol}//${location.host}/ws/run/${runId}?from=${fromIndex}`);

    ws.onopen = () => {
        reconnectAttempts = 0;
        setWsIndicator("live");
    };

    ws.onmessage = (event) => {
        eventsSeen += 1;
        const data = JSON.parse(event.data);
        handleRunEvent(data);
    };

    ws.onclose = () => {
        if (runTerminal) {
            return;
        }
        if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
            setStatus(`${currentRunLabel}: connection lost -- task may still be running`);
            setWsIndicator("disconnected");
            setRunningUiState(false);
            return;
        }
        const delay = RECONNECT_BASE_DELAY_MS * Math.pow(2, reconnectAttempts);
        reconnectAttempts += 1;
        setStatus(`${currentRunLabel}: connection lost, reconnecting...`);
        setWsIndicator("reconnecting");
        setTimeout(() => connectWebSocket(runId, eventsSeen), delay);
    };
}

// ---- Output file downloads --------------------------------------------------

function clearRunOutputs() {
    const container = document.getElementById("output-downloads");
    container.innerHTML = "";
    container.classList.add("d-none");
}

function showRunOutputs(runId) {
    fetch(`/api/run/${runId}/outputs`)
        .then((r) => r.json())
        .then((groups) => {
            const container = document.getElementById("output-downloads");
            container.innerHTML = "";
            if (!groups.length) {
                container.classList.add("d-none");
                return;
            }
            for (const group of groups) {
                const header = document.createElement("div");
                header.className = "fw-semibold small mt-1";
                header.textContent = group.task;
                container.appendChild(header);
                for (const file of group.files) {
                    const link = document.createElement("a");
                    link.className = "d-block small";
                    if (file.exists) {
                        link.href = `/api/run/${runId}/outputs/${encodeURIComponent(group.module)}/${encodeURIComponent(group.task)}/${encodeURIComponent(file.script_name)}/download`;
                        link.textContent = `${file.script_name}: ${file.value}`;
                    } else {
                        link.href = "#";
                        link.classList.add("text-muted", "disabled");
                        link.textContent = `${file.script_name}: ${file.value} (not found on disk)`;
                    }
                    container.appendChild(link);
                }
            }
            container.classList.remove("d-none");
        });
}

function handleRunEvent(data) {
    if (data.type === "output") {
        appendLog(data.line);
    } else if (data.type === "step") {
        const iterDesc =
            data.total_iterations > 1
                ? ` iteration ${data.iteration_index}/${data.total_iterations} (${Object.entries(
                      data.iteration_values || {}
                  )
                      .map(([k, v]) => `${k}=${v}`)
                      .join(", ")})`
                : "";
        const message = `Running ${currentRunLabel} [${data.step_index}/${data.total_steps}]: ${data.task_name}${iterDesc}...`;
        setStatus(message);
        appendLog(`=== [${data.step_index}/${data.total_steps}] ${data.task_name}${iterDesc} ===`);
    } else if (data.type === "done") {
        runTerminal = true;
        setRunningUiState(false);
        setWsIndicator("idle");
        const status = data.returncode === 0 ? "succeeded" : `failed (exit code ${data.returncode})`;
        appendLog(`${currentRunLabel}, finished`);
        setStatus(`${currentRunLabel} ${status}`);
        if (data.returncode === 0 && currentRunId) {
            showRunOutputs(currentRunId);
        }
        if (selection) {
            // Refresh the detail panel so a newly recorded history value shows up.
            if (selection.kind === "task") selectTask(selection.module, selection.name);
            else selectPipeline(selection.module, selection.name);
        }
    } else if (data.type === "error") {
        runTerminal = true;
        setRunningUiState(false);
        setWsIndicator("idle");
        appendLog(`${currentRunLabel}: ${data.message}`);
        setStatus(`${currentRunLabel} failed to start: ${data.message}`);
    }
}

applySavedLayout();
setupTreeResize();
setupOutputResize();
loadProjectTitle();
loadTree();
