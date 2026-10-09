"""
Tests for the input-file pre-flight check: ExecutionEngine.check_input_files /
check_pipeline_input_files, and how the CLI (model_flow.py) and the web GUI
(web_gui/server.py) refuse a run when input files are missing.
"""
import json

import pytest

import model_flow
from classes.Config import Config
from classes.ExecutionEngine import ExecutionEngine
from web_gui.server import create_app


def config_data(tmp_path) -> dict:
    return {
        "Code_directory": str(tmp_path),
        "Database_directory": str(tmp_path),
        "Temporary_directory": str(tmp_path),
        "Rscript_exe": "C:/R/Rscript.exe",
        "GAMS_exe": "C:/GAMS/gams.exe",
    }


def make_config(tmp_path) -> Config:
    return Config(json.dumps(config_data(tmp_path)))


def task(name, inputs=(), outputs=()):
    """A task dict whose input_file/output_file values are relative to
    Database_directory (no relative attribute -> resolved against it)."""
    config = [{"name": "ext_par", "role": "parameter", "script_name": "ext_par", "script_value": "5"}]
    config += [{"name": n, "role": "input_file", "script_name": n, "script_value": v} for n, v in inputs]
    config += [{"name": n, "role": "output_file", "script_name": n, "script_value": v} for n, v in outputs]
    return {"module": "m", "file": f"{name}.R", "file_path": f"C:/scripts/{name}.R", "filetype": ".r",
            "name": name, "description": "", "config": config}


def write_db(tmp_path, tasks, pipelines=None, lists=None):
    (tmp_path / "model_flow.db.json").write_text(json.dumps({"m": tasks}), encoding="utf-8")
    if pipelines is not None:
        (tmp_path / "model_flow.pipelines.json").write_text(json.dumps({"m": pipelines}), encoding="utf-8")
    if lists is not None:
        (tmp_path / "model_flow.lists.json").write_text(json.dumps({"lists": lists}), encoding="utf-8")


def entry(name, overrides=None, loop=None):
    return {"task": name, "overrides": overrides or {}, "loop": loop}


@pytest.fixture
def fake_execute_task(monkeypatch):
    calls = []

    def _fake(self, module, task_name, output_dir=None, overrides=None, **kwargs):
        calls.append((task_name, overrides))
        return 0

    monkeypatch.setattr(ExecutionEngine, "execute_task", _fake)
    return calls


# ---- ExecutionEngine.check_input_files --------------------------------------

def test_check_input_files_reports_only_missing_inputs(tmp_path):
    (tmp_path / "present.csv").write_text("x", encoding="utf-8")
    write_db(tmp_path, [task("t", inputs=[("a", "present.csv"), ("b", "missing.csv")])])

    problems = ExecutionEngine(make_config(tmp_path)).check_input_files("m", "t")

    assert problems == [{"task": "t", "script_name": "b", "path": str(tmp_path / "missing.csv"), "status": "missing"}]


def test_check_input_files_uses_override_value(tmp_path):
    (tmp_path / "present.csv").write_text("x", encoding="utf-8")
    write_db(tmp_path, [task("t", inputs=[("a", "missing.csv")])])
    engine = ExecutionEngine(make_config(tmp_path))

    assert engine.check_input_files("m", "t", {"a": "present.csv"}) == []


def test_check_input_files_reports_inaccessible_input(tmp_path, monkeypatch):
    import pathlib
    locked = tmp_path / "locked.csv"
    real_exists = pathlib.Path.exists

    def fake_exists(self, *args, **kwargs):
        if self == locked:
            raise PermissionError(13, "Access is denied", str(self))
        return real_exists(self, *args, **kwargs)

    write_db(tmp_path, [task("t", inputs=[("a", "locked.csv")])])
    engine = ExecutionEngine(make_config(tmp_path))
    monkeypatch.setattr(pathlib.Path, "exists", fake_exists)

    assert [p["status"] for p in engine.check_input_files("m", "t")] == ["no_access"]


# ---- ExecutionEngine.check_pipeline_input_files -----------------------------

def test_pipeline_skips_inputs_produced_by_an_earlier_step(tmp_path):
    write_db(
        tmp_path,
        [task("produce", outputs=[("out", "mid.csv")]), task("consume", inputs=[("in", "mid.csv"), ("x", "raw.csv")])],
        pipelines=[{"name": "p", "tasks": [entry("produce"), entry("consume")]}],
    )

    problems = ExecutionEngine(make_config(tmp_path)).check_pipeline_input_files("m", "p")

    # mid.csv doesn't exist yet but "produce" writes it first; raw.csv is genuinely missing.
    assert [p["script_name"] for p in problems] == ["x"]


def test_pipeline_still_reports_input_produced_only_by_a_later_step(tmp_path):
    write_db(
        tmp_path,
        [task("produce", outputs=[("out", "mid.csv")]), task("consume", inputs=[("in", "mid.csv")])],
        pipelines=[{"name": "p", "tasks": [entry("consume"), entry("produce")]}],
    )

    problems = ExecutionEngine(make_config(tmp_path)).check_pipeline_input_files("m", "p")

    assert [p["task"] for p in problems] == ["consume"]


def test_pipeline_parallel_group_members_do_not_produce_for_each_other(tmp_path):
    write_db(
        tmp_path,
        [task("produce", outputs=[("out", "mid.csv")]), task("consume", inputs=[("in", "mid.csv")])],
        pipelines=[{"name": "p", "tasks": [
            {"parallel": [entry("produce"), entry("consume")], "max_workers": None},
        ]}],
    )

    problems = ExecutionEngine(make_config(tmp_path)).check_pipeline_input_files("m", "p")

    assert [p["task"] for p in problems] == ["consume"]


def test_pipeline_checks_every_loop_iteration_value(tmp_path):
    (tmp_path / "AT.csv").write_text("x", encoding="utf-8")
    loop = {"parameters": {"in": "countries"}, "combine": None, "mode": "sequential", "max_workers": None}
    write_db(
        tmp_path,
        [task("t", inputs=[("in", "default.csv")])],
        pipelines=[{"name": "p", "tasks": [entry("t", loop=loop)]}],
        lists=[{"name": "countries", "type": "string", "elements": ["AT.csv", "BE.csv"]}],
    )

    problems = ExecutionEngine(make_config(tmp_path)).check_pipeline_input_files("m", "p")

    assert [p["path"] for p in problems] == [str(tmp_path / "BE.csv")]


# ---- CLI (model_flow.py) ------------------------------------------------------

def test_cli_run_task_refuses_and_does_not_run(tmp_path, fake_execute_task):
    write_db(tmp_path, [task("t", inputs=[("a", "missing.csv")])])

    with pytest.raises(model_flow.MissingInputFilesError, match="--ignore-missing-inputs"):
        model_flow.run_task(make_config(tmp_path), "m", "t")
    assert fake_execute_task == []


def test_cli_run_task_runs_anyway_with_ignore_missing_inputs(tmp_path, fake_execute_task):
    write_db(tmp_path, [task("t", inputs=[("a", "missing.csv")])])

    model_flow.run_task(make_config(tmp_path), "m", "t", ignore_missing_inputs=True)

    assert [c[0] for c in fake_execute_task] == ["t"]


def test_cli_run_pipeline_refuses_and_runs_nothing(tmp_path, fake_execute_task):
    write_db(
        tmp_path,
        [task("ok"), task("needs", inputs=[("a", "missing.csv")])],
        pipelines=[{"name": "p", "tasks": [entry("ok"), entry("needs")]}],
    )

    with pytest.raises(model_flow.MissingInputFilesError):
        model_flow.run_pipeline(make_config(tmp_path), "m", "p")
    assert fake_execute_task == []  # not even the first, unaffected step

    assert model_flow.run_pipeline(make_config(tmp_path), "m", "p", ignore_missing_inputs=True) == 0
    assert [c[0] for c in fake_execute_task] == ["ok", "needs"]


def test_cli_main_exits_nonzero_when_refused(tmp_path, fake_execute_task, monkeypatch):
    write_db(tmp_path, [task("t", inputs=[("a", "missing.csv")])])
    (tmp_path / "model_flow.config.json").write_text(json.dumps(config_data(tmp_path)), encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["model_flow.py", "run_task", f"--config={tmp_path}", "--module=m", "--task=t"])

    with pytest.raises(SystemExit) as exc:
        model_flow.main()
    assert exc.value.code == 1
    assert fake_execute_task == []


# ---- Web GUI (web_gui/server.py) ---------------------------------------------

def test_web_run_task_refused_with_missing_inputs_and_not_started(tmp_path, fake_execute_task):
    write_db(tmp_path, [task("t", inputs=[("a", "missing.csv")])])
    client = create_app(make_config(tmp_path)).test_client()

    resp = client.post("/api/run_task", json={"module": "m", "task": "t"})

    assert resp.status_code == 400
    body = resp.get_json()
    assert "run_id" not in body
    assert body["missing_inputs"] == [f"t: a = {tmp_path / 'missing.csv'} (does not exist)"]
    assert fake_execute_task == []


def test_web_run_task_override_fixing_the_input_is_allowed(tmp_path, fake_execute_task):
    (tmp_path / "present.csv").write_text("x", encoding="utf-8")
    write_db(tmp_path, [task("t", inputs=[("a", "missing.csv")])])
    client = create_app(make_config(tmp_path)).test_client()

    resp = client.post("/api/run_task", json={"module": "m", "task": "t", "overrides": {"a": "present.csv"}})

    assert resp.status_code == 200
    assert "run_id" in resp.get_json()


def test_web_run_pipeline_refused_with_missing_inputs(tmp_path, fake_execute_task):
    write_db(
        tmp_path,
        [task("needs", inputs=[("a", "missing.csv")])],
        pipelines=[{"name": "p", "tasks": [entry("needs")]}],
    )
    client = create_app(make_config(tmp_path)).test_client()

    resp = client.post("/api/run_pipeline", json={"module": "m", "pipeline": "p"})

    assert resp.status_code == 400
    assert len(resp.get_json()["missing_inputs"]) == 1
    assert fake_execute_task == []


def test_pipeline_check_skips_a_loop_it_cannot_expand(tmp_path):
    """A loop over a list that doesn't exist is left for the run itself to
    report -- the pre-flight check must not crash on it."""
    loop = {"parameters": {"in": "no_such_list"}, "combine": None, "mode": "sequential", "max_workers": None}
    write_db(tmp_path, [task("t", inputs=[("in", "default.csv")])],
             pipelines=[{"name": "p", "tasks": [entry("t", loop=loop)]}])

    assert ExecutionEngine(make_config(tmp_path)).check_pipeline_input_files("m", "p") == []
