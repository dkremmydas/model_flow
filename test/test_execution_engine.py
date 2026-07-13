import pytest

from classes import ExecutionEngine as execution_engine_module
from classes.Config import Config
from classes.ExecutionEngine import ExecutionEngine


@pytest.fixture
def engine(tmp_path):
    (tmp_path / "model_flow.db.json").write_text("{}", encoding="utf-8")
    config_data = {
        "Code_directory": str(tmp_path),
        "Database_directory": str(tmp_path),
        "Temporary_directory": str(tmp_path),
        "Rscript_exe": "C:/R/Rscript.exe",
        "GAMS_exe": "C:/GAMS/gams.exe",
        "Pandoc_dir": "C:/Pandoc",
    }
    import json

    config = Config(json.dumps(config_data))
    return ExecutionEngine(config)


@pytest.fixture
def fake_call(monkeypatch):
    calls = []

    def _fake_call(command):
        calls.append(command)
        return 0

    monkeypatch.setattr(execution_engine_module.subprocess, "call", _fake_call)
    return calls


def test_execute_r_task_builds_command_with_forward_slashes(engine, fake_call):
    task = {
        "file_path": "C:\\scripts\\test_script.R",
        "config": [{"script_name": "ext_par", "script_value": "5"}],
    }

    result = engine._execute_r_task(task)

    assert result == 0
    assert fake_call == [
        ["C:\\R\\Rscript.exe", "C:/scripts/test_script.R", "ext_par=5"]
    ]


def test_execute_gams_task_does_not_convert_backslashes(engine, fake_call):
    task = {
        "file_path": "C:\\gams\\test_script.gms",
        "config": [{"script_name": "limit", "script_value": "15"}],
    }

    result = engine._execute_gams_task(task)

    assert result == 0
    assert fake_call == [
        ["C:\\GAMS\\gams.exe", "C:\\gams\\test_script.gms", "limit=15"]
    ]


def test_execute_rmd_task_sets_gams_dir_on_path(engine, fake_call, tmp_path):
    task = {
        "name": "1_test_rmd",
        "file_path": "C:\\scripts\\test_script.rmd",
        "config": [{"script_name": "external_data", "script_value": "5", "type": "number"}],
    }

    result = engine._execute_rmd_task(task, output_dir=str(tmp_path))

    assert result == 0
    assert len(fake_call) == 1
    command = fake_call[0]
    assert command[0] == "C:\\R\\Rscript.exe"
    assert command[1] == "-e"
    render_script = command[2]
    assert "Sys.setenv(RSTUDIO_PANDOC='C:/Pandoc')" in render_script
    assert "paste('C:/GAMS'" in render_script
    assert "rmarkdown::render(" in render_script
    assert "input = 'C:/scripts/test_script.rmd'" in render_script
