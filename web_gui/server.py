"""
Minimal local web GUI for Model Flow: a thin Flask + WebSocket front end over
the same Database/ExecutionEngine/Lists/Parser classes the Textual GUI
(textual_gui/app.py) and CLI (model_flow.py) already use. No new business
logic lives here -- every route is a small wrapper around an existing method.

Streaming (task/pipeline/rebuild output) uses a WebSocket with reconnect-and-
catch-up rather than a one-shot streamed HTTP response: a POST to
/api/run_task, /api/run_pipeline, or /api/rebuild starts the work on a
background thread and returns a run_id immediately; the browser then opens
/ws/run/<run_id>?from=<n> to receive events from index n onward, live plus
whatever was buffered while it wasn't connected. This lets a dropped browser
connection (sleep, backgrounded tab, brief network hiccup) reconnect and
catch up instead of losing the rest of a long-running task's output.
"""

import json
import threading
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from flask import Flask, jsonify, request, send_file, send_from_directory
from flask_sock import Sock

from classes.Config import Config
from classes.Database import Database
from classes.ExecutionEngine import ExecutionEngine, ExecutionResult
from classes.FileInspector import FileInspector
from classes.FileStatus import file_status as _file_status, file_statuses as _file_statuses
from classes.Lists import Lists
from classes.Parser import Parser

STATIC_DIR = Path(__file__).parent / "static"

# How many *finished* runs to keep buffered after they complete, purely so a
# client reconnecting shortly after a run ends can still catch up on its
# tail end -- not intended as persistent run history.
MAX_FINISHED_RUNS = 5


@dataclass
class RunRecord:
    """One run's (task, pipeline, or rebuild) append-only event log, the
    source of truth for both live streaming and reconnect catch-up."""
    events: List[dict] = field(default_factory=list)
    condition: threading.Condition = field(default_factory=threading.Condition)
    done: bool = False
    # Every subprocess.Popen started by this run (via on_process_start) -- a list,
    # since a parallel loop or parallel pipeline group runs several at once.
    processes: List[object] = field(default_factory=list)
    # [{"module", "task", "overrides"}] for each task that actually ran in this
    # run -- one entry for a single task run, one per non-looped pipeline step
    # for a pipeline run. Populated at run start, used by /api/run/<id>/outputs
    # to resolve role="output_file" config entries against what was actually run.
    outputs_info: List[dict] = field(default_factory=list)

    def append(self, event: dict) -> None:
        with self.condition:
            self.events.append(event)
            self.condition.notify_all()

    def finish(self) -> None:
        with self.condition:
            self.done = True
            self.condition.notify_all()


class RunState:
    """Tracks the single in-flight run (if any) plus a small bounded history
    of recently finished runs, so a reconnect just after completion still
    resolves. One run at a time, matching the Textual GUI's own guard."""

    def __init__(self) -> None:
        self.active_run_id: Optional[str] = None
        self.runs: "OrderedDict[str, RunRecord]" = OrderedDict()
        self._lock = threading.Lock()

    def start_run(self):
        """Atomically create a new RunRecord iff no run is currently active.
        Returns (run_id, record), or None if a run is already in progress."""
        with self._lock:
            active = self.runs.get(self.active_run_id) if self.active_run_id else None
            if active is not None and not active.done:
                return None

            run_id = uuid.uuid4().hex
            record = RunRecord()
            self.runs[run_id] = record
            self.active_run_id = run_id
            self._evict_finished_locked()
            return run_id, record

    def _evict_finished_locked(self) -> None:
        finished_ids = [rid for rid, r in self.runs.items() if r.done and rid != self.active_run_id]
        while len(self.runs) > MAX_FINISHED_RUNS + 1 and finished_ids:
            del self.runs[finished_ids.pop(0)]

    def finish_active(self) -> None:
        with self._lock:
            self.active_run_id = None

    def get(self, run_id: str) -> Optional[RunRecord]:
        with self._lock:
            return self.runs.get(run_id)

    def get_active(self) -> Optional[RunRecord]:
        with self._lock:
            if self.active_run_id is None:
                return None
            return self.runs.get(self.active_run_id)


def _launch(run_state: RunState, work) -> Optional[str]:
    """Start `work(record) -> returncode` on a background thread if no run is
    active. `work` is responsible for wiring on_output/on_process_start (and,
    for a pipeline, on_step_start) to `record.append`. Appends a final
    done/error event and releases the active-run slot when work finishes."""
    started = run_state.start_run()
    if started is None:
        return None
    run_id, record = started

    def worker():
        try:
            returncode = work(record)
            record.append({"type": "done", "returncode": returncode})
        except Exception as e:
            record.append({"type": "error", "message": str(e)})
        finally:
            record.finish()
            run_state.finish_active()

    threading.Thread(target=worker, daemon=True).start()
    return run_id


def _describe_loop(loop: Dict) -> str:
    """One-line, read-only summary of a pipeline task's loop declaration, e.g.
    "Looped over nuts_code=nuts2 (parallel, up to 8 workers)". Mirrors
    textual_gui/app.py's ShowTask._describe_loop."""
    params_desc = ", ".join(f"{param}={list_name}" for param, list_name in loop.get("parameters", {}).items())
    mode = loop.get("mode", "sequential")
    max_workers = loop.get("max_workers")
    mode_desc = f"parallel, up to {max_workers} workers" if mode == "parallel" and max_workers else mode
    return f"Looped over {params_desc} ({mode_desc})"


def create_app(config: Config) -> Flask:
    app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="")
    sock = Sock(app)

    database = Database(config)
    engine = ExecutionEngine(config)
    lists = Lists(config)
    run_state = RunState()

    def refuse_missing_inputs(problems: List[Dict]):
        """400 refusal for a run whose input files are missing or
        inaccessible (ExecutionEngine.check_input_files), or None if there are
        none. Unlike the CLI there is no override -- the run is not started."""
        if not problems:
            return None
        return jsonify({
            "error": f"Not run: {len(problems)} input file(s) missing or inaccessible",
            "missing_inputs": ExecutionEngine.describe_input_file_problems(problems),
        }), 400

    def with_input_file_status(configs: List[tuple]) -> List[List[Dict]]:
        """For each (task_config, overrides) pair, a copy of task_config where
        every role="input_file" entry also carries "file_status" (see
        _file_status; checked live, like api_graph's link["exists"]) for its
        effective value -- the pipeline's override if one is given, else its
        script_value. Every pair's files are checked in one concurrent batch
        (see _file_statuses). Copies rather than mutating, since these dicts
        are the Database's own cached task data."""
        resolved_by_param = {}
        for config_index, (task_config, overrides) in enumerate(configs):
            for param_index, param in enumerate(task_config):
                if param.get("role") == "input_file" and param.get("script_name"):
                    value = str((overrides or {}).get(param["script_name"], param.get("script_value") or ""))
                    resolved_by_param[(config_index, param_index)] = (
                        Parser.resolve_role_path(config.get("Database_directory"), value, param.get("relative"))
                        if value else None
                    )
        statuses = _file_statuses(p for p in resolved_by_param.values() if p is not None)

        result = []
        for config_index, (task_config, _) in enumerate(configs):
            new_config = []
            for param_index, param in enumerate(task_config):
                if (config_index, param_index) in resolved_by_param:
                    resolved = resolved_by_param[(config_index, param_index)]
                    # resolved_path: where it actually looked (a relative value is
                    # resolved against Database_directory), for the hover note.
                    param = {**param, "file_status": statuses[str(resolved)] if resolved else "missing",
                             "resolved_path": str(resolved) if resolved else ""}
                new_config.append(param)
            result.append(new_config)
        return result

    @app.route("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")

    @app.route("/api/config")
    def api_config():
        return jsonify({
            "project_title": config.get("Project_title"),
            "database_directory": config.get("Database_directory"),
        })

    @app.route("/api/tree")
    def api_tree():
        return jsonify([
            {
                "module": module,
                "tasks": database.list_module_tasks(module),
                # Kept as a separate name -> filetype map rather than turning
                # "tasks" into objects, since the frontend matches/selects tasks
                # by plain name string throughout.
                "task_types": {
                    task["name"]: task.get("filetype", "")
                    for task in database.get_module(module) or []
                },
                "pipelines": database.list_pipelines(module),
            }
            for module in database.list_modules()
        ])

    # <path:module> rather than the default <module> converter -- a task's
    # @MODELFLOW_task module="..." attribute is a free-form string that some
    # codebases use to mirror nested folder structure (e.g. "v.main2020/d.policy"),
    # and the default converter's regex excludes "/", which would 404 for any
    # such module even though the frontend correctly percent-encodes the slash.
    @app.route("/api/task/<path:module>/<task_name>")
    def api_task(module, task_name):
        task = database.get_task(module, task_name)
        if task is None:
            return jsonify({"error": "task not found"}), 404
        task = {**task, "config": with_input_file_status([(task.get("config", []), None)])[0]}
        return jsonify({"task": task, "history": database.get_user_values(module, task_name)})

    @app.route("/api/pipeline/<path:module>/<pipeline_name>")  # see api_task's comment above
    def api_pipeline(module, pipeline_name):
        pipeline = database.get_pipeline(module, pipeline_name)
        if pipeline is None:
            return jsonify({"error": "pipeline not found"}), 404

        tasks = []
        group_workers = {
            step_index: step.get("max_workers")
            for step_index, step in enumerate(pipeline.get("tasks", []), start=1)
            if isinstance(step, dict) and "parallel" in step
        }
        for entry, group in Parser.iter_pipeline_entries(pipeline.get("tasks", [])):
            task_name = entry["task"]
            task = database.get_task(module, task_name)
            loop = entry.get("loop")
            tasks.append({
                "task_name": task_name,
                "overrides": entry.get("overrides") or {},
                "loop": loop,
                "loop_summary": _describe_loop(loop) if loop else None,
                # Step number of the parallel group this task belongs to (None if
                # it's an ordinary step), so the page can show which tasks run together.
                "parallel_group": group,
                "parallel_group_workers": group_workers.get(group) if group else None,
                "config": task.get("config", []) if task else [],
                "overrides_for_status": entry.get("overrides"),
                "history": database.get_user_values(module, task_name) if task else {},
            })

        # Every task's input files checked in one concurrent batch.
        checked = with_input_file_status([(t["config"], t.pop("overrides_for_status")) for t in tasks])
        for task_entry, task_config in zip(tasks, checked):
            task_entry["config"] = task_config

        return jsonify({"pipeline": pipeline, "tasks": tasks})

    @app.route("/api/run_task", methods=["POST"])
    def api_run_task():
        body = request.get_json(force=True, silent=True) or {}
        module = body.get("module")
        task_name = body.get("task")
        overrides = body.get("overrides") or {}
        if not module or not task_name:
            return jsonify({"error": "'module' and 'task' are required"}), 400
        refusal = refuse_missing_inputs(engine.check_input_files(module, task_name, overrides or None))
        if refusal:
            return refusal

        def work(record: RunRecord):
            record.outputs_info = [{"module": module, "task": task_name, "overrides": overrides}]

            def on_output(line):
                record.append({"type": "output", "line": line})

            def on_process_start(process):
                record.processes.append(process)

            result = engine.execute_task(
                module, task_name, overrides=overrides or None, capture_output=True,
                on_output=on_output, on_process_start=on_process_start,
            )
            for script_name, value in overrides.items():
                database.add_user_value(module, task_name, script_name, value)
            return result.returncode if isinstance(result, ExecutionResult) else result

        run_id = _launch(run_state, work)
        if run_id is None:
            return jsonify({"error": "a run is already in progress"}), 409
        return jsonify({"run_id": run_id})

    @app.route("/api/run_pipeline", methods=["POST"])
    def api_run_pipeline():
        body = request.get_json(force=True, silent=True) or {}
        module = body.get("module")
        pipeline_name = body.get("pipeline")
        extra_overrides = body.get("overrides") or {}
        if not module or not pipeline_name:
            return jsonify({"error": "'module' and 'pipeline' are required"}), 400
        try:
            problems = engine.check_pipeline_input_files(module, pipeline_name, extra_overrides)
        except ValueError as e:
            return jsonify({"error": str(e)}), 404
        refusal = refuse_missing_inputs(problems)
        if refusal:
            return refusal

        def work(record: RunRecord):
            # One entry per non-looped step, with the same overrides merge order
            # ExecutionEngine.execute_pipeline itself uses (entry's own "overrides"
            # then extra_overrides) -- looped steps are skipped since a loop's
            # output path may vary per iteration and isn't tracked per-iteration here.
            pipeline = database.get_pipeline(module, pipeline_name) or {}
            outputs_info = []
            for entry, _group in Parser.iter_pipeline_entries(pipeline.get("tasks", [])):
                if entry.get("loop"):
                    continue
                step_task_name = entry["task"]
                merged = {**(entry.get("overrides") or {}), **extra_overrides.get(step_task_name, {})}
                outputs_info.append({"module": module, "task": step_task_name, "overrides": merged})
            record.outputs_info = outputs_info

            def on_output(line):
                record.append({"type": "output", "line": line})

            def on_process_start(process):
                record.processes.append(process)

            # "key" (ExecutionEngine.execution_key) ties a step's output lines and
            # its end result back to it, so the page can show per-task status and
            # output when several run in parallel.
            def on_step_output(key, line):
                record.append({"type": "output", "line": line, "key": key})

            def on_step_end(key, returncode):
                record.append({"type": "step_end", "key": key, "returncode": returncode})

            def on_step_start(step_index, total_steps, task_name, iteration_index,
                               total_iterations, iteration_values):
                record.append({
                    "type": "step",
                    "key": ExecutionEngine.execution_key(step_index, task_name, iteration_index),
                    "step_index": step_index,
                    "total_steps": total_steps,
                    "task_name": task_name,
                    "iteration_index": iteration_index,
                    "total_iterations": total_iterations,
                    "iteration_values": iteration_values,
                })

            returncode = engine.execute_pipeline(
                module, pipeline_name, capture_output=True,
                on_output=on_output, on_process_start=on_process_start, on_step_start=on_step_start,
                extra_overrides=extra_overrides or None,
                on_step_output=on_step_output, on_step_end=on_step_end,
            )
            for task_name, task_overrides in extra_overrides.items():
                for script_name, value in task_overrides.items():
                    database.add_user_value(module, task_name, script_name, value)
            return returncode

        run_id = _launch(run_state, work)
        if run_id is None:
            return jsonify({"error": "a run is already in progress"}), 409
        return jsonify({"run_id": run_id})

    @app.route("/api/rebuild", methods=["POST"])
    def api_rebuild():
        code_directory = config.get("Code_directory")

        def work(record: RunRecord):
            def on_file(path):
                record.append({"type": "output", "line": f"Scanning: {path}"})

            modules = Parser.parse_modules(code_directory, on_file)
            lists_data = Parser.parse_lists(code_directory, on_file)
            pipelines = Parser.parse_pipelines(code_directory, modules, lists_data, on_file)
            graph = Parser.build_graph(modules, config.get("Database_directory"))
            (Path(config.get("Database_directory")) / Parser.graph_filename).write_text(
                json.dumps(graph, indent=2), encoding="utf-8"
            )

            database.data = modules
            database.save()
            database.pipelines_data = pipelines
            database.save_pipelines()
            lists.lists_data = lists_data
            lists.save()
            # ExecutionEngine owns its own separate Database/Lists instances --
            # update them too, or a run started right after this rebuild would
            # still use the stale pre-rebuild definitions (mirrors
            # textual_gui/app.py's action_rebuild_database).
            engine.database.data = modules
            engine.database.pipelines_data = pipelines
            engine.lists.lists_data = lists_data

            module_count = len(modules)
            task_count = sum(len(tasks) for tasks in modules.values())
            pipeline_count = sum(len(p) for p in pipelines.values())
            list_count = len(lists_data)
            record.append({
                "type": "output",
                "line": f"Database rebuilt: {module_count} modules, {task_count} tasks, "
                        f"{pipeline_count} pipelines, {list_count} lists, {len(graph['links'])} file links",
            })
            return 0

        run_id = _launch(run_state, work)
        if run_id is None:
            return jsonify({"error": "a run is already in progress"}), 409
        return jsonify({"run_id": run_id})

    @app.route("/api/kill", methods=["POST"])
    def api_kill():
        record = run_state.get_active()
        live = [process for process in record.processes if process.poll() is None] if record else []
        if not live:
            return jsonify({"error": "no running task to kill"}), 409
        for process in live:
            process.terminate()
        return jsonify({"ok": True})

    def _load_graph():
        """Read graph.json fresh (never cached -- mirrors api_graph's own
        no-caching contract), or None if it hasn't been built yet."""
        graph_path = Path(config.get("Database_directory")) / Parser.graph_filename
        if not graph_path.exists():
            return None
        return json.loads(graph_path.read_text(encoding="utf-8"))

    @app.route("/api/graph")
    def api_graph():
        graph = _load_graph()
        if graph is None:
            return jsonify({"error": "no graph built yet -- run rebuild first"}), 404
        # exists is computed live on every request, not baked in at build time
        # -- a file's existence changes as tasks run, independent of when the
        # graph itself was last rebuilt (mirrors /api/run/<id>/outputs' own
        # {"exists": resolved.exists()} pattern). .exists() rather than
        # .is_file() since an input/output can also be a folder.
        # An inaccessible file isn't known to be missing, so it isn't drawn as
        # "not created yet"; no_access lets the map flag it separately.
        links = graph.get("links", [])
        statuses = _file_statuses(link["file"] for link in links)
        for link in links:
            status = statuses[str(Path(link["file"]))]
            link["exists"] = status != "missing"
            link["no_access"] = status == "no_access"
        return jsonify(graph)

    @app.route("/api/inspect")
    def api_inspect():
        file_path = request.args.get("file")
        if not file_path:
            return jsonify({"error": "'file' query parameter is required"}), 400

        # This is the first route that reads arbitrary file *contents* off
        # disk (every other route only ever send_file's a path resolved from
        # a known task's own config) -- restrict it to files the current
        # graph actually knows about (or, for drilling into a folder link's
        # own contents, a path living inside one of those known folders)
        # rather than letting it become a general arbitrary-file-read endpoint.
        graph = _load_graph() or {}
        known_files = {link["file"] for link in graph.get("links", [])}
        if file_path not in known_files:
            resolved_target = Path(file_path).resolve()
            allowed = any(
                Path(known).is_dir() and resolved_target.is_relative_to(Path(known).resolve())
                for known in known_files
            )
            if not allowed:
                return jsonify({"error": "file is not part of the dependency graph"}), 403

        resolved = Path(file_path)
        status = _file_status(resolved)
        if status == "no_access":
            return jsonify({"exists": True, "error": "No permission to access this file."}), 403
        if status == "missing":
            # Race-condition backstop -- the frontend already knows a file's
            # existence from /api/graph and won't normally offer to inspect
            # one it knows doesn't exist yet. .exists() rather than
            # .is_file() since an input/output can also be a folder.
            return jsonify({"exists": False})

        try:
            data = FileInspector.inspect_path(resolved, config)
        except Exception as e:
            return jsonify({"exists": True, "error": str(e)}), 500
        return jsonify({"exists": True, "data": data})

    @app.route("/api/run/<run_id>/outputs")
    def api_run_outputs(run_id):
        record = run_state.get(run_id)
        if record is None:
            return jsonify({"error": "unknown run_id"}), 404

        result = []
        for info in record.outputs_info:
            task = database.get_task(info["module"], info["task"])
            if task is None:
                continue
            files = []
            for param in task.get("config", []):
                script_name = param.get("script_name")
                if param.get("role") != "output_file" or not script_name:
                    continue
                value = info["overrides"].get(script_name, param.get("script_value"))
                if value is None:
                    continue
                resolved = Parser.resolve_role_path(config.get("Database_directory"), value, param.get("relative"))
                status = _file_status(resolved)
                files.append({"script_name": script_name, "value": value,
                              "exists": status == "exists", "no_access": status == "no_access"})
            if files:
                result.append({"module": info["module"], "task": info["task"], "files": files})
        return jsonify(result)

    # <path:module> for the same reason api_task/api_pipeline use it -- see their comment above.
    @app.route("/api/run/<run_id>/outputs/<path:module>/<task_name>/<script_name>/download")
    def api_download_output(run_id, module, task_name, script_name):
        record = run_state.get(run_id)
        if record is None:
            return jsonify({"error": "unknown run_id"}), 404

        info = next((i for i in record.outputs_info if i["module"] == module and i["task"] == task_name), None)
        if info is None:
            return jsonify({"error": "not found"}), 404

        task = database.get_task(module, task_name)
        param = next(
            (p for p in (task.get("config", []) if task else [])
             if p.get("role") == "output_file" and p.get("script_name") == script_name),
            None,
        )
        if param is None:
            return jsonify({"error": "not an output_file parameter"}), 404

        value = info["overrides"].get(script_name, param.get("script_value"))
        resolved = Parser.resolve_role_path(config.get("Database_directory"), value, param.get("relative"))
        if _file_status(resolved) == "no_access":
            return jsonify({"error": "no permission to access this file"}), 403
        if not resolved.is_file():
            return jsonify({"error": "file not found on disk"}), 404
        return send_file(resolved, as_attachment=True)

    @sock.route("/ws/run/<run_id>")
    def ws_run(ws, run_id):
        record = run_state.get(run_id)
        if record is None:
            ws.send(json.dumps({"type": "error", "message": "unknown run_id"}))
            return

        from_index = int(request.args.get("from", 0))
        while True:
            with record.condition:
                record.condition.wait_for(lambda: len(record.events) > from_index or record.done)
                new_events = record.events[from_index:]
                from_index = len(record.events)
                done = record.done
            for event in new_events:
                ws.send(json.dumps(event))
            if done:
                break

    return app
