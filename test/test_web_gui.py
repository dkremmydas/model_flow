"""
Tests for web_gui/server.py.

Plain HTTP routes are exercised with Flask's built-in test_client() (no new
dependency needed for that). RunRecord/RunState's buffering and catch-up
logic is tested directly as plain Python -- no socket involved. The actual
WebSocket wire behavior (live push, disconnect-and-reconnect catch-up, kill)
needs a real client against a real running server, so those tests start the
app on an ephemeral localhost port (via werkzeug's make_server, for a clean
shutdown) and drive it with the `websockets` package.
"""
import asyncio
import json
import threading
import time

import pytest
from werkzeug.serving import make_server

from classes import ExecutionEngine as execution_engine_module
from classes.Config import Config
from web_gui.server import RunRecord, RunState, create_app

MAX_FINISHED_RUNS = 5


def make_config(tmp_path) -> Config:
    config_data = {
        "Code_directory": str(tmp_path),
        "Database_directory": str(tmp_path),
        "Temporary_directory": str(tmp_path),
        "Rscript_exe": "C:/R/Rscript.exe",
        "GAMS_exe": "C:/GAMS/gams.exe",
        "Pandoc_dir": "C:/Pandoc",
    }
    return Config(json.dumps(config_data))


def write_db_with_one_task(tmp_path):
    db_content = {
        "test_module": [
            {
                "module": "test_module",
                "file": "script.R",
                "file_path": "C:\\scripts\\test_script.R",
                "filetype": ".r",
                "name": "1_test_task",
                "description": "A test task.",
                "config": [
                    {
                        "name": "ext_par",
                        "role": "parameter",
                        "type": "number",
                        "script_name": "ext_par",
                        "script_value": "5",
                    }
                ],
            }
        ]
    }
    (tmp_path / "model_flow.db.json").write_text(json.dumps(db_content), encoding="utf-8")


def write_db_with_one_task_and_looped_pipeline(tmp_path):
    write_db_with_one_task(tmp_path)
    pipelines_content = {
        "test_module": [
            {
                "name": "full_run",
                "description": "Runs everything.",
                "tasks": [
                    {
                        "task": "1_test_task",
                        "overrides": {},
                        "loop": {
                            "parameters": {"ext_par": "some_list"},
                            "combine": None,
                            "mode": "sequential",
                            "max_workers": None,
                        },
                    }
                ],
            }
        ]
    }
    (tmp_path / "model_flow.pipelines.json").write_text(json.dumps(pipelines_content), encoding="utf-8")


def write_db_with_output_file_task(tmp_path):
    """A task with one role="output_file" config entry (relative="0", so its
    script_value is resolved as an absolute path as-is) alongside a plain
    parameter -- for exercising /api/run/<id>/outputs and the download route."""
    db_content = {
        "test_module": [
            {
                "module": "test_module",
                "file": "script.R",
                "file_path": "C:\\scripts\\test_script.R",
                "filetype": ".r",
                "name": "1_test_task",
                "description": "A test task.",
                "config": [
                    {
                        "name": "ext_par",
                        "role": "parameter",
                        "type": "number",
                        "script_name": "ext_par",
                        "script_value": "5",
                    },
                    {
                        "name": "output_file",
                        "role": "output_file",
                        "relative": "0",
                        "script_name": "output_file",
                        "script_value": str(tmp_path / "default_output.csv"),
                    },
                ],
            }
        ]
    }
    (tmp_path / "model_flow.db.json").write_text(json.dumps(db_content), encoding="utf-8")


# ---------------------------------------------------------------------------
# Plain HTTP routes (Flask test_client, no real server/socket needed)
# ---------------------------------------------------------------------------

def test_api_tree_lists_modules_tasks_and_pipelines(tmp_path):
    write_db_with_one_task_and_looped_pipeline(tmp_path)
    client = create_app(make_config(tmp_path)).test_client()

    resp = client.get("/api/tree")
    assert resp.status_code == 200
    assert resp.get_json() == [
        {"module": "test_module", "tasks": ["1_test_task"], "pipelines": ["full_run"]}
    ]


def test_api_task_returns_config_and_history(tmp_path):
    write_db_with_one_task(tmp_path)
    client = create_app(make_config(tmp_path)).test_client()

    resp = client.get("/api/task/test_module/1_test_task")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["task"]["name"] == "1_test_task"
    assert body["task"]["config"][0]["script_value"] == "5"
    assert body["history"] == {}


def test_api_task_unknown_returns_404(tmp_path):
    write_db_with_one_task(tmp_path)
    client = create_app(make_config(tmp_path)).test_client()

    resp = client.get("/api/task/test_module/does_not_exist")
    assert resp.status_code == 404


def write_db_with_slash_in_module_name(tmp_path):
    """Some codebases give a task's @MODELFLOW_task module="..." attribute a
    value that mirrors nested folder structure, e.g. "v.main2020/d.policy" --
    a real module name, containing a literal '/', not a routing artifact."""
    db_content = {
        "v.main2020/d.policy": [
            {
                "module": "v.main2020/d.policy",
                "file": "script.R",
                "file_path": "C:\\scripts\\policy.R",
                "filetype": ".r",
                "name": "1_create_policy_data",
                "description": "",
                "config": [],
            }
        ]
    }
    (tmp_path / "model_flow.db.json").write_text(json.dumps(db_content), encoding="utf-8")


def test_api_task_handles_slash_in_module_name(tmp_path):
    """Regression test: Flask's default route converter excludes '/', so a module
    name containing one (mirroring nested folder structure) 404'd even though the
    frontend correctly percent-encodes it as %2F -- the fix is <path:module>."""
    write_db_with_slash_in_module_name(tmp_path)
    client = create_app(make_config(tmp_path)).test_client()

    resp = client.get("/api/task/v.main2020%2Fd.policy/1_create_policy_data")
    assert resp.status_code == 200
    assert resp.get_json()["task"]["name"] == "1_create_policy_data"


def test_api_pipeline_returns_per_task_config_and_loop_summary(tmp_path):
    write_db_with_one_task_and_looped_pipeline(tmp_path)
    client = create_app(make_config(tmp_path)).test_client()

    resp = client.get("/api/pipeline/test_module/full_run")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["pipeline"]["name"] == "full_run"
    task_entry = body["tasks"][0]
    assert task_entry["task_name"] == "1_test_task"
    assert task_entry["loop"]["parameters"] == {"ext_par": "some_list"}
    assert task_entry["loop_summary"] == "Looped over ext_par=some_list (sequential)"


def test_api_pipeline_handles_slash_in_module_name(tmp_path):
    write_db_with_slash_in_module_name(tmp_path)
    pipelines_content = {
        "v.main2020/d.policy": [
            {"name": "full_run", "description": "", "tasks": ["1_create_policy_data"]}
        ]
    }
    (tmp_path / "model_flow.pipelines.json").write_text(json.dumps(pipelines_content), encoding="utf-8")
    client = create_app(make_config(tmp_path)).test_client()

    resp = client.get("/api/pipeline/v.main2020%2Fd.policy/full_run")
    assert resp.status_code == 200
    assert resp.get_json()["pipeline"]["name"] == "full_run"


def test_api_run_task_missing_fields_returns_400(tmp_path):
    write_db_with_one_task(tmp_path)
    client = create_app(make_config(tmp_path)).test_client()

    resp = client.post("/api/run_task", json={"module": "test_module"})
    assert resp.status_code == 400


def test_api_kill_without_active_run_returns_409(tmp_path):
    write_db_with_one_task(tmp_path)
    client = create_app(make_config(tmp_path)).test_client()

    resp = client.post("/api/kill")
    assert resp.status_code == 409


def test_run_outputs_unknown_run_id_returns_404(tmp_path):
    write_db_with_one_task(tmp_path)
    client = create_app(make_config(tmp_path)).test_client()

    resp = client.get("/api/run/does-not-exist/outputs")
    assert resp.status_code == 404


def test_download_output_unknown_run_id_returns_404(tmp_path):
    write_db_with_one_task(tmp_path)
    client = create_app(make_config(tmp_path)).test_client()

    resp = client.get("/api/run/does-not-exist/outputs/test_module/1_test_task/output_file/download")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# RunRecord / RunState: pure Python, no socket needed
# ---------------------------------------------------------------------------

def test_run_record_append_wakes_a_waiting_reader():
    record = RunRecord()
    received = []

    def reader():
        with record.condition:
            record.condition.wait_for(lambda: len(record.events) > 0)
            received.append(record.events[0])

    t = threading.Thread(target=reader)
    t.start()
    time.sleep(0.05)  # let the reader thread reach wait_for before we append
    record.append({"type": "output", "line": "hello"})
    t.join(timeout=5)

    assert received == [{"type": "output", "line": "hello"}]


def test_run_state_blocks_second_run_while_first_still_active():
    state = RunState()
    started = state.start_run()
    assert started is not None
    run_id, record = started

    assert state.start_run() is None  # a run is already active

    record.finish()
    state.finish_active()

    second = state.start_run()
    assert second is not None
    assert second[0] != run_id


def test_run_state_evicts_oldest_finished_runs_beyond_cap():
    state = RunState()
    run_ids = []
    for _ in range(MAX_FINISHED_RUNS + 3):
        run_id, record = state.start_run()
        record.finish()
        state.finish_active()
        run_ids.append(run_id)

    # The most recently finished runs (up to the cap) must still be retrievable;
    # the oldest ones must have been evicted.
    assert state.get(run_ids[-1]) is not None
    assert state.get(run_ids[0]) is None


# ---------------------------------------------------------------------------
# WebSocket streaming: a real server + a real client, since this is the one
# genuinely new kind of test this feature needs (not covered by test_client()).
# ---------------------------------------------------------------------------

class _FakePopenMultiLine:
    """Produces a fixed sequence of lines and exits cleanly -- used for the
    live-streaming and reconnect-catch-up tests, where the exact timing of
    disconnect/reconnect doesn't matter (RunRecord buffers everything
    regardless of whether a reader was connected when it happened)."""

    def __init__(self, command, stdout=None, stderr=None, text=None, bufsize=None, env=None):
        self.stdout = iter(["line1\n", "line2\n", "line3\n"])
        self.returncode = 0

    def wait(self):
        return self.returncode

    def poll(self):
        return self.returncode


class _FakePopenBlockingUntilTerminated:
    """Mirrors test_execution_engine.py's fake_popen_killable, but blocks on a
    threading.Event instead of spinning, so a kill test doesn't burn CPU
    waiting to be terminated."""

    def __init__(self, command, stdout=None, stderr=None, text=None, bufsize=None, env=None):
        self._terminated = threading.Event()
        self.returncode = None
        self.stdout = self._make_stdout()

    def _make_stdout(self):
        yield "starting\n"
        self._terminated.wait(timeout=5)

    def terminate(self):
        self.returncode = 1
        self._terminated.set()

    def wait(self):
        if self.returncode is None:
            self.returncode = 0
        return self.returncode

    def poll(self):
        return self.returncode


class _LiveServer:
    """A real Flask app served on an ephemeral localhost port, for tests that
    need a genuine WebSocket connection rather than Flask's test_client()."""

    def __init__(self, app):
        self._server = make_server("127.0.0.1", 0, app, threaded=True)
        self.port = self._server.server_port
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc_info):
        self._server.shutdown()
        self._thread.join(timeout=5)

    @property
    def base_url(self):
        return f"ws://127.0.0.1:{self.port}"


async def _collect_ws_events(url):
    import websockets

    events = []
    async with websockets.connect(url) as ws:
        while True:
            message = await asyncio.wait_for(ws.recv(), timeout=5)
            data = json.loads(message)
            events.append(data)
            if data["type"] in ("done", "error"):
                break
    return events


def test_websocket_streams_live_output_and_records_history(tmp_path, monkeypatch):
    monkeypatch.setattr(execution_engine_module.subprocess, "Popen", _FakePopenMultiLine)
    write_db_with_one_task(tmp_path)
    app = create_app(make_config(tmp_path))

    with _LiveServer(app) as server:
        client = app.test_client()
        resp = client.post(
            "/api/run_task",
            json={"module": "test_module", "task": "1_test_task", "overrides": {"ext_par": "99"}},
        )
        assert resp.status_code == 200
        run_id = resp.get_json()["run_id"]

        events = asyncio.run(_collect_ws_events(f"{server.base_url}/ws/run/{run_id}?from=0"))

        assert [e["line"] for e in events if e["type"] == "output"] == ["line1", "line2", "line3"]
        assert events[-1] == {"type": "done", "returncode": 0}

        history = client.get("/api/task/test_module/1_test_task").get_json()["history"]
        assert history == {"ext_par": ["99"]}


def test_run_outputs_lists_output_file_entries_after_run(tmp_path, monkeypatch):
    monkeypatch.setattr(execution_engine_module.subprocess, "Popen", _FakePopenMultiLine)
    write_db_with_output_file_task(tmp_path)
    app = create_app(make_config(tmp_path))

    with _LiveServer(app) as server:
        client = app.test_client()
        resp = client.post("/api/run_task", json={"module": "test_module", "task": "1_test_task"})
        run_id = resp.get_json()["run_id"]
        asyncio.run(_collect_ws_events(f"{server.base_url}/ws/run/{run_id}?from=0"))

        outputs = client.get(f"/api/run/{run_id}/outputs").get_json()
        assert outputs == [
            {
                "module": "test_module",
                "task": "1_test_task",
                "files": [
                    {
                        "script_name": "output_file",
                        "value": str(tmp_path / "default_output.csv"),
                        "exists": False,
                    }
                ],
            }
        ]


def test_run_outputs_reflects_override_used_for_that_run(tmp_path, monkeypatch):
    monkeypatch.setattr(execution_engine_module.subprocess, "Popen", _FakePopenMultiLine)
    write_db_with_output_file_task(tmp_path)
    app = create_app(make_config(tmp_path))
    override_path = tmp_path / "custom_output.csv"
    override_path.write_text("actual output", encoding="utf-8")

    with _LiveServer(app) as server:
        client = app.test_client()
        resp = client.post(
            "/api/run_task",
            json={"module": "test_module", "task": "1_test_task", "overrides": {"output_file": str(override_path)}},
        )
        run_id = resp.get_json()["run_id"]
        asyncio.run(_collect_ws_events(f"{server.base_url}/ws/run/{run_id}?from=0"))

        outputs = client.get(f"/api/run/{run_id}/outputs").get_json()
        files = outputs[0]["files"]
        assert files == [{"script_name": "output_file", "value": str(override_path), "exists": True}]


def test_download_output_returns_file_content_when_it_exists(tmp_path, monkeypatch):
    monkeypatch.setattr(execution_engine_module.subprocess, "Popen", _FakePopenMultiLine)
    write_db_with_output_file_task(tmp_path)
    app = create_app(make_config(tmp_path))
    (tmp_path / "default_output.csv").write_bytes(b"a,b\n1,2\n")

    with _LiveServer(app) as server:
        client = app.test_client()
        resp = client.post("/api/run_task", json={"module": "test_module", "task": "1_test_task"})
        run_id = resp.get_json()["run_id"]
        asyncio.run(_collect_ws_events(f"{server.base_url}/ws/run/{run_id}?from=0"))

        download = client.get(f"/api/run/{run_id}/outputs/test_module/1_test_task/output_file/download")
        assert download.status_code == 200
        assert download.data == b"a,b\n1,2\n"


def test_download_output_returns_404_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(execution_engine_module.subprocess, "Popen", _FakePopenMultiLine)
    write_db_with_output_file_task(tmp_path)
    app = create_app(make_config(tmp_path))

    with _LiveServer(app) as server:
        client = app.test_client()
        resp = client.post("/api/run_task", json={"module": "test_module", "task": "1_test_task"})
        run_id = resp.get_json()["run_id"]
        asyncio.run(_collect_ws_events(f"{server.base_url}/ws/run/{run_id}?from=0"))

        download = client.get(f"/api/run/{run_id}/outputs/test_module/1_test_task/output_file/download")
        assert download.status_code == 404


def test_run_pipeline_outputs_excludes_looped_tasks(tmp_path, monkeypatch):
    monkeypatch.setattr(execution_engine_module.subprocess, "Popen", _FakePopenMultiLine)

    db_content = {
        "test_module": [
            {
                "module": "test_module", "file": "a.R", "file_path": "C:\\scripts\\a.R", "filetype": ".r",
                "name": "plain_task", "description": "",
                "config": [
                    {"name": "output_file", "role": "output_file", "relative": "0",
                     "script_name": "output_file", "script_value": str(tmp_path / "plain_output.csv")},
                ],
            },
            {
                "module": "test_module", "file": "b.R", "file_path": "C:\\scripts\\b.R", "filetype": ".r",
                "name": "looped_task", "description": "",
                "config": [
                    {"name": "output_file", "role": "output_file", "relative": "0",
                     "script_name": "output_file", "script_value": str(tmp_path / "looped_output.csv")},
                ],
            },
        ]
    }
    (tmp_path / "model_flow.db.json").write_text(json.dumps(db_content), encoding="utf-8")
    pipelines_content = {
        "test_module": [
            {
                "name": "mixed_pipeline",
                "description": "",
                "tasks": [
                    "plain_task",
                    {
                        "task": "looped_task",
                        "overrides": {},
                        "loop": {
                            "parameters": {"ext_par": "some_list"},
                            "combine": None,
                            "mode": "sequential",
                            "max_workers": None,
                        },
                    },
                ],
            }
        ]
    }
    (tmp_path / "model_flow.pipelines.json").write_text(json.dumps(pipelines_content), encoding="utf-8")
    (tmp_path / "model_flow.lists.json").write_text(
        json.dumps({"some_list": {"name": "some_list", "type": "string", "elements": ["A", "B"]}}),
        encoding="utf-8",
    )

    app = create_app(make_config(tmp_path))

    with _LiveServer(app) as server:
        client = app.test_client()
        resp = client.post("/api/run_pipeline", json={"module": "test_module", "pipeline": "mixed_pipeline"})
        run_id = resp.get_json()["run_id"]
        asyncio.run(_collect_ws_events(f"{server.base_url}/ws/run/{run_id}?from=0"))

        outputs = client.get(f"/api/run/{run_id}/outputs").get_json()
        assert [group["task"] for group in outputs] == ["plain_task"]


def test_websocket_reconnect_catches_up_missed_events_without_duplicates(tmp_path, monkeypatch):
    monkeypatch.setattr(execution_engine_module.subprocess, "Popen", _FakePopenMultiLine)
    write_db_with_one_task(tmp_path)
    app = create_app(make_config(tmp_path))

    with _LiveServer(app) as server:
        client = app.test_client()
        resp = client.post("/api/run_task", json={"module": "test_module", "task": "1_test_task"})
        run_id = resp.get_json()["run_id"]

        async def scenario():
            import websockets

            first_batch = []
            async with websockets.connect(f"{server.base_url}/ws/run/{run_id}?from=0") as ws:
                message = await asyncio.wait_for(ws.recv(), timeout=5)
                first_batch.append(json.loads(message))
            # connection dropped here -- reconnect picking up from where we left off
            remaining = await _collect_ws_events(f"{server.base_url}/ws/run/{run_id}?from={len(first_batch)}")
            return first_batch, remaining

        first_batch, remaining = asyncio.run(scenario())

        assert first_batch == [{"type": "output", "line": "line1"}]
        assert remaining == [
            {"type": "output", "line": "line2"},
            {"type": "output", "line": "line3"},
            {"type": "done", "returncode": 0},
        ]


def test_kill_terminates_running_process_via_api(tmp_path, monkeypatch):
    monkeypatch.setattr(execution_engine_module.subprocess, "Popen", _FakePopenBlockingUntilTerminated)
    write_db_with_one_task(tmp_path)
    app = create_app(make_config(tmp_path))

    with _LiveServer(app) as server:
        client = app.test_client()
        resp = client.post("/api/run_task", json={"module": "test_module", "task": "1_test_task"})
        run_id = resp.get_json()["run_id"]

        async def scenario():
            import websockets

            async with websockets.connect(f"{server.base_url}/ws/run/{run_id}?from=0") as ws:
                # Wait for the process's first output line, so we know
                # on_process_start has already fired and /api/kill has a
                # live process to terminate.
                first = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
                assert first == {"type": "output", "line": "starting"}

                kill_resp = client.post("/api/kill")
                assert kill_resp.status_code == 200

                rest = [first]
                while True:
                    message = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
                    rest.append(message)
                    if message["type"] == "done":
                        break
                return rest

        events = asyncio.run(scenario())
        assert events[-1] == {"type": "done", "returncode": 1}


def test_run_task_returns_409_while_another_run_is_active(tmp_path, monkeypatch):
    monkeypatch.setattr(execution_engine_module.subprocess, "Popen", _FakePopenBlockingUntilTerminated)
    write_db_with_one_task(tmp_path)
    app = create_app(make_config(tmp_path))
    client = app.test_client()

    resp = client.post("/api/run_task", json={"module": "test_module", "task": "1_test_task"})
    assert resp.status_code == 200

    # Give the worker thread a moment to reach on_process_start so the run is
    # genuinely active (not just "recorded" but not yet actually started).
    time.sleep(0.1)

    second = client.post("/api/run_task", json={"module": "test_module", "task": "1_test_task"})
    assert second.status_code == 409

    kill_resp = client.post("/api/kill")
    assert kill_resp.status_code == 200
