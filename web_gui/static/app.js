// Model Flow web GUI client. Plain vanilla JS, no build step: fetches JSON
// from /api/*, renders the module/task/pipeline tree and a config-edit form,
// and streams a run's output over a WebSocket that reconnects (with capped
// backoff) and catches up on missed events if the connection drops.

const MAX_RECONNECT_ATTEMPTS = 5;
const RECONNECT_BASE_DELAY_MS = 1000;

let treeData = [];
let selection = null; // {kind: "task"|"pipeline", module, name}
let taskDefaults = {}; // script_name -> default value, for the selected task
let pipelineRows = []; // [{taskName, scriptName, inputId, defaultValue}], for the selected pipeline

let ws = null;
let eventsSeen = 0;
let reconnectAttempts = 0;
let runTerminal = false; // true once a "done"/"error" event has been received for the current run
let currentRunLabel = "";

function sanitizeId(value) {
    return String(value).replace(/[^a-zA-Z0-9_-]/g, "_");
}

// ---- Tree ----------------------------------------------------------------

function loadTree() {
    fetch("/api/tree")
        .then((r) => r.json())
        .then((data) => {
            treeData = data;
            renderTree(document.getElementById("search-input").value);
        });
}

function renderTree(query) {
    query = (query || "").trim().toLowerCase();
    const container = document.getElementById("tree-container");
    container.innerHTML = "";

    for (const entry of treeData) {
        const moduleMatches = entry.module.toLowerCase().includes(query);
        const matchingTasks = moduleMatches ? entry.tasks : entry.tasks.filter((t) => t.toLowerCase().includes(query));
        const matchingPipelines = moduleMatches
            ? entry.pipelines
            : entry.pipelines.filter((p) => p.toLowerCase().includes(query));

        if (!moduleMatches && matchingTasks.length === 0 && matchingPipelines.length === 0) {
            continue;
        }

        const moduleHeader = document.createElement("div");
        moduleHeader.className = "tree-module";
        moduleHeader.textContent = entry.module;
        container.appendChild(moduleHeader);

        if (matchingTasks.length) {
            const tasksLabel = document.createElement("div");
            tasksLabel.className = "tree-group";
            tasksLabel.textContent = "Tasks";
            container.appendChild(tasksLabel);
            for (const taskName of matchingTasks) {
                container.appendChild(makeTreeItem(entry.module, taskName, "task"));
            }
        }

        if (matchingPipelines.length) {
            const pipelinesLabel = document.createElement("div");
            pipelinesLabel.className = "tree-group";
            pipelinesLabel.textContent = "Pipelines";
            container.appendChild(pipelinesLabel);
            for (const pipelineName of matchingPipelines) {
                container.appendChild(makeTreeItem(entry.module, pipelineName, "pipeline"));
            }
        }
    }
}

function makeTreeItem(module, name, kind) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "tree-item";
    btn.textContent = name;
    btn.addEventListener("click", () => {
        document.querySelectorAll("#tree-container .tree-item.active").forEach((el) => el.classList.remove("active"));
        btn.classList.add("active");
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
            document.getElementById("detail-description").textContent = data.task.description || "";

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
            document.getElementById("detail-description").textContent = data.pipeline.description || "";

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
            document.getElementById("output-log").textContent = "";
            setStatus(`Running ${label}... `);
            setRunningUiState(true);
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

// ---- WebSocket streaming with reconnect-and-catch-up -----------------------

function connectWebSocket(runId, fromIndex) {
    const protocol = location.protocol === "https:" ? "wss:" : "ws:";
    ws = new WebSocket(`${protocol}//${location.host}/ws/run/${runId}?from=${fromIndex}`);

    ws.onopen = () => {
        reconnectAttempts = 0;
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
            setRunningUiState(false);
            return;
        }
        const delay = RECONNECT_BASE_DELAY_MS * Math.pow(2, reconnectAttempts);
        reconnectAttempts += 1;
        setStatus(`${currentRunLabel}: connection lost, reconnecting...`);
        setTimeout(() => connectWebSocket(runId, eventsSeen), delay);
    };
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
        const status = data.returncode === 0 ? "succeeded" : `failed (exit code ${data.returncode})`;
        appendLog(`${currentRunLabel}, finished`);
        setStatus(`${currentRunLabel} ${status}`);
        if (selection) {
            // Refresh the detail panel so a newly recorded history value shows up.
            if (selection.kind === "task") selectTask(selection.module, selection.name);
            else selectPipeline(selection.module, selection.name);
        }
    } else if (data.type === "error") {
        runTerminal = true;
        setRunningUiState(false);
        appendLog(`${currentRunLabel}: ${data.message}`);
        setStatus(`${currentRunLabel} failed to start: ${data.message}`);
    }
}

loadTree();
