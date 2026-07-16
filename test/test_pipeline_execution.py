import json

import pytest

import model_flow
from classes.Config import Config
from classes.ExecutionEngine import ExecutionEngine


def make_config(tmp_path) -> Config:
    config_data = {
        "Code_directory": str(tmp_path),
        "Database_directory": str(tmp_path),
        "Temporary_directory": str(tmp_path),
        "Rscript_exe": "C:/R/Rscript.exe",
        "GAMS_exe": "C:/GAMS/gams.exe",
    }
    return Config(json.dumps(config_data))


def write_pipeline(tmp_path, module, name, tasks):
    (tmp_path / "model_flow.db.json").write_text("{}", encoding="utf-8")
    pipelines_data = {module: [{"name": name, "description": "", "tasks": tasks}]}
    (tmp_path / "model_flow.pipelines.json").write_text(json.dumps(pipelines_data), encoding="utf-8")


@pytest.fixture
def fake_execute_task(monkeypatch):
    calls = []
    results = {"queue": None}

    def _fake_execute_task(self, module, task_name, output_dir=None, overrides=None, **kwargs):
        calls.append((module, task_name, output_dir))
        if results["queue"] is not None:
            return results["queue"].pop(0)
        return 0

    monkeypatch.setattr(ExecutionEngine, "execute_task", _fake_execute_task)
    return calls, results


def test_run_pipeline_runs_all_tasks_in_order_and_returns_zero_on_success(tmp_path, fake_execute_task):
    calls, _ = fake_execute_task
    write_pipeline(tmp_path, "test_module", "run_all", ["1_task", "2_task", "3_task"])

    result = model_flow.run_pipeline(make_config(tmp_path), "test_module", "run_all")

    assert result == 0
    assert [c[1] for c in calls] == ["1_task", "2_task", "3_task"]


def test_run_pipeline_stops_at_first_failing_task(tmp_path, fake_execute_task):
    calls, results = fake_execute_task
    results["queue"] = [0, 1, 0]
    write_pipeline(tmp_path, "test_module", "run_all", ["1_task", "2_task", "3_task"])

    result = model_flow.run_pipeline(make_config(tmp_path), "test_module", "run_all")

    assert result == 1
    assert [c[1] for c in calls] == ["1_task", "2_task"]  # 3_task never called


def test_run_pipeline_raises_value_error_for_unknown_pipeline(tmp_path, fake_execute_task):
    (tmp_path / "model_flow.db.json").write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="not found"):
        model_flow.run_pipeline(make_config(tmp_path), "test_module", "does_not_exist")


def test_run_pipeline_passes_output_dir_through_to_every_task(tmp_path, fake_execute_task):
    calls, _ = fake_execute_task
    write_pipeline(tmp_path, "test_module", "run_all", ["1_task", "2_task"])

    model_flow.run_pipeline(make_config(tmp_path), "test_module", "run_all", output_dir="C:/custom_out")

    assert [c[2] for c in calls] == ["C:/custom_out", "C:/custom_out"]
