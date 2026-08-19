import json
import subprocess

import pytest

from classes import RdsInspector as rds_inspector_module
from classes.Config import Config
from classes.RdsInspector import RdsInspector


def make_config(tmp_path) -> Config:
    config_data = {
        "Code_directory": str(tmp_path),
        "Database_directory": str(tmp_path),
        "Temporary_directory": str(tmp_path),
        "Rscript_exe": "C:/R/Rscript.exe",
        "GAMS_exe": "C:/GAMS/gams.exe",
    }
    return Config(json.dumps(config_data))


def make_fake_run(stdout="", stderr="", returncode=0):
    """
    Canned subprocess.run replacement -- RdsInspector shells out to a
    machine-specific Rscript_exe path (unlike GdxInspector's portable pip
    dependency), so tests mock the subprocess call rather than exercising a
    real R install, following this codebase's established rule (see
    test_execution_engine.py's fake_run) of never invoking a real
    R/GAMS-family executable in tests.
    """
    calls = []

    def _fake_run(command, capture_output=True, text=True):
        calls.append(command)
        return subprocess.CompletedProcess(command, returncode=returncode, stdout=stdout, stderr=stderr)

    return _fake_run, calls


def touch_rds(tmp_path, name="model.rds"):
    path = tmp_path / name
    path.write_bytes(b"")  # content is irrelevant -- Rscript itself is mocked
    return path


def test_inspect_data_frame(tmp_path, monkeypatch):
    stdout = json.dumps({
        "classes": ["data.frame"],
        "primary_class": "data.frame",
        "detail": {
            "kind": "data_frame", "rows": 3, "columns": 2,
            "column_names": ["a", "b"], "column_classes": ["integer", "character"],
        },
    })
    fake_run, calls = make_fake_run(stdout=stdout)
    monkeypatch.setattr(rds_inspector_module.subprocess, "run", fake_run)
    rds_path = touch_rds(tmp_path)

    result = RdsInspector(make_config(tmp_path)).inspect(rds_path)

    assert result == {
        "format": "rds-object",
        "classes": ["data.frame"],
        "primary_class": "data.frame",
        "detail": {
            "kind": "data_frame", "rows": 3, "columns": 2,
            "column_names": ["a", "b"], "column_classes": ["integer", "character"],
        },
    }
    # Invoked Rscript_exe with the inspect_rds.R script path and the target file.
    command = calls[0]
    assert command[0] == "C:/R/Rscript.exe"
    assert command[1].endswith("inspect_rds.R")
    assert command[2] == str(rds_path)


def test_inspect_data_table_gets_data_frame_detail_but_reports_data_table_class(tmp_path, monkeypatch):
    stdout = json.dumps({
        "classes": ["data.table", "data.frame"],
        "primary_class": "data.table",
        "detail": {
            "kind": "data_frame", "rows": 3, "columns": 2,
            "column_names": ["a", "b"], "column_classes": ["integer", "character"],
        },
    })
    fake_run, _ = make_fake_run(stdout=stdout)
    monkeypatch.setattr(rds_inspector_module.subprocess, "run", fake_run)

    result = RdsInspector(make_config(tmp_path)).inspect(touch_rds(tmp_path))

    assert result["classes"] == ["data.table", "data.frame"]
    assert result["primary_class"] == "data.table"
    assert result["detail"]["kind"] == "data_frame"


def test_inspect_matrix(tmp_path, monkeypatch):
    stdout = json.dumps({
        "classes": ["matrix", "array"],
        "primary_class": "matrix",
        "detail": {"kind": "matrix", "dim": [2, 3], "type": "integer"},
    })
    fake_run, _ = make_fake_run(stdout=stdout)
    monkeypatch.setattr(rds_inspector_module.subprocess, "run", fake_run)

    result = RdsInspector(make_config(tmp_path)).inspect(touch_rds(tmp_path))

    assert result["detail"] == {"kind": "matrix", "dim": [2, 3], "type": "integer"}


def test_inspect_list(tmp_path, monkeypatch):
    stdout = json.dumps({
        "classes": ["list"],
        "primary_class": "list",
        "detail": {
            "kind": "list", "length": 3, "names": ["x", "y", "z"],
            "element_classes": ["integer", "character", "list"],
        },
    })
    fake_run, _ = make_fake_run(stdout=stdout)
    monkeypatch.setattr(rds_inspector_module.subprocess, "run", fake_run)

    result = RdsInspector(make_config(tmp_path)).inspect(touch_rds(tmp_path))

    assert result["detail"]["length"] == 3
    assert result["detail"]["names"] == ["x", "y", "z"]


def test_inspect_unhandled_class_reports_class_only(tmp_path, monkeypatch):
    stdout = json.dumps({"classes": ["lm"], "primary_class": "lm", "detail": None})
    fake_run, _ = make_fake_run(stdout=stdout)
    monkeypatch.setattr(rds_inspector_module.subprocess, "run", fake_run)

    result = RdsInspector(make_config(tmp_path)).inspect(touch_rds(tmp_path))

    assert result == {"format": "rds-object", "classes": ["lm"], "primary_class": "lm", "detail": None}


def test_inspect_missing_file_raises_without_calling_subprocess(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        rds_inspector_module.subprocess, "run",
        lambda *a, **k: calls.append(1),
    )

    with pytest.raises(FileNotFoundError):
        RdsInspector(make_config(tmp_path)).inspect(tmp_path / "does_not_exist.rds")

    assert calls == []


def test_inspect_missing_rscript_exe_raises_value_error(tmp_path):
    config_data = {
        "Code_directory": str(tmp_path),
        "Database_directory": str(tmp_path),
        "Temporary_directory": str(tmp_path),
        "Rscript_exe": "",
        "GAMS_exe": "C:/GAMS/gams.exe",
    }
    config = Config(json.dumps(config_data))

    with pytest.raises(ValueError):
        RdsInspector(config).inspect(touch_rds(tmp_path))


def test_inspect_nonzero_exit_raises_runtime_error(tmp_path, monkeypatch):
    fake_run, _ = make_fake_run(returncode=1, stderr="readRDS: file is corrupt")
    monkeypatch.setattr(rds_inspector_module.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError):
        RdsInspector(make_config(tmp_path)).inspect(touch_rds(tmp_path))


def test_inspect_malformed_stdout_raises_runtime_error(tmp_path, monkeypatch):
    fake_run, _ = make_fake_run(stdout="not json")
    monkeypatch.setattr(rds_inspector_module.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError):
        RdsInspector(make_config(tmp_path)).inspect(touch_rds(tmp_path))
