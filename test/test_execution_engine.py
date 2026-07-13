import json

import pytest

from classes import ExecutionEngine as execution_engine_module
from classes.Config import Config
from classes.ExecutionEngine import ExecutionEngine, ExecutionResult


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


@pytest.fixture
def engine(tmp_path):
    (tmp_path / "model_flow.db.json").write_text("{}", encoding="utf-8")
    return ExecutionEngine(make_config(tmp_path))


@pytest.fixture
def engine_without_pandoc(tmp_path):
    (tmp_path / "model_flow.db.json").write_text("{}", encoding="utf-8")
    config_data = {
        "Code_directory": str(tmp_path),
        "Database_directory": str(tmp_path),
        "Temporary_directory": str(tmp_path),
        "Rscript_exe": "C:/R/Rscript.exe",
        "GAMS_exe": "C:/GAMS/gams.exe",
        # Pandoc_dir intentionally omitted, matching a real config that predates it.
    }
    return ExecutionEngine(Config(json.dumps(config_data)))


@pytest.fixture
def engine_with_task(tmp_path):
    db_content = {
        "test_module": [
            {
                "module": "test_module",
                "file": "script.R",
                "file_path": "C:\\scripts\\test_script.R",
                "filetype": ".r",
                "name": "1_test_task",
                "description": "",
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
    return ExecutionEngine(make_config(tmp_path))


@pytest.fixture
def fake_call(monkeypatch):
    calls = []

    def _fake_call(command):
        calls.append(command)
        return 0

    monkeypatch.setattr(execution_engine_module.subprocess, "call", _fake_call)
    return calls


@pytest.fixture
def fake_run(monkeypatch):
    import subprocess as std_subprocess

    calls = []

    def _fake_run(command, capture_output=True, text=True):
        calls.append(command)
        return std_subprocess.CompletedProcess(command, returncode=0, stdout="hello output", stderr="")

    monkeypatch.setattr(execution_engine_module.subprocess, "run", _fake_run)
    return calls


@pytest.fixture
def fake_popen(monkeypatch):
    calls = []

    class FakePopen:
        def __init__(self, command, stdout=None, stderr=None, text=None, bufsize=None):
            calls.append(command)
            self.stdout = iter(["line1\n", "line2\n"])
            self.returncode = 0

        def wait(self):
            return self.returncode

    monkeypatch.setattr(execution_engine_module.subprocess, "Popen", FakePopen)
    return calls


@pytest.fixture
def fake_popen_killable(monkeypatch):
    """A FakePopen whose stdout never stops producing lines until terminate() is
    called, so tests can exercise 'process was killed mid-stream' deterministically."""
    calls = []

    class FakePopen:
        def __init__(self, command, stdout=None, stderr=None, text=None, bufsize=None):
            calls.append(command)
            self._terminated = False
            self.returncode = None
            self.stdout = self._make_stdout()

        def _make_stdout(self):
            i = 0
            while not self._terminated:
                i += 1
                yield f"line{i}\n"

        def terminate(self):
            self._terminated = True
            self.returncode = 1

        def wait(self):
            if self.returncode is None:
                self.returncode = 0
            return self.returncode

        def poll(self):
            return self.returncode

    monkeypatch.setattr(execution_engine_module.subprocess, "Popen", FakePopen)
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


def test_execute_task_applies_overrides_without_mutating_database(engine_with_task, fake_call):
    result = engine_with_task.execute_task("test_module", "1_test_task", overrides={"ext_par": "99"})

    assert result == 0
    assert fake_call == [["C:\\R\\Rscript.exe", "C:/scripts/test_script.R", "ext_par=99"]]

    original = engine_with_task.database.get_task("test_module", "1_test_task")
    assert original["config"][0]["script_value"] == "5"


def test_execute_task_without_overrides_uses_database_defaults(engine_with_task, fake_call):
    result = engine_with_task.execute_task("test_module", "1_test_task")

    assert result == 0
    assert fake_call == [["C:\\R\\Rscript.exe", "C:/scripts/test_script.R", "ext_par=5"]]


def test_execute_rmd_task_raises_clear_error_when_pandoc_dir_missing(engine_without_pandoc, fake_call):
    task = {
        "name": "1_test_rmd",
        "file_path": "C:\\scripts\\test_script.rmd",
        "config": [],
    }

    with pytest.raises(ValueError, match="Pandoc_dir"):
        engine_without_pandoc._execute_rmd_task(task, output_dir=".")

    assert fake_call == []  # must fail before ever building/running a command


def test_execute_r_task_capture_output_returns_execution_result(engine, fake_run):
    task = {
        "file_path": "C:\\scripts\\test_script.R",
        "config": [{"script_name": "ext_par", "script_value": "5"}],
    }

    result = engine._execute_r_task(task, capture_output=True)

    assert isinstance(result, ExecutionResult)
    assert result.returncode == 0
    assert result.stdout == "hello output"
    assert fake_run == [["C:\\R\\Rscript.exe", "C:/scripts/test_script.R", "ext_par=5"]]


def test_execute_r_task_streams_output_via_on_output(engine, fake_popen):
    task = {
        "file_path": "C:\\scripts\\test_script.R",
        "config": [{"script_name": "ext_par", "script_value": "5"}],
    }
    received = []

    result = engine._execute_r_task(task, capture_output=True, on_output=received.append)

    assert received == ["line1", "line2"]  # streamed as they were produced, not after the fact
    assert isinstance(result, ExecutionResult)
    assert result.returncode == 0
    assert result.stdout == "line1\nline2"
    assert fake_popen == [["C:\\R\\Rscript.exe", "C:/scripts/test_script.R", "ext_par=5"]]


def test_execute_task_streams_output_end_to_end_with_overrides(engine_with_task, fake_popen):
    received = []

    result = engine_with_task.execute_task(
        "test_module", "1_test_task", overrides={"ext_par": "99"}, capture_output=True, on_output=received.append
    )

    assert received == ["line1", "line2"]
    assert isinstance(result, ExecutionResult)
    assert fake_popen == [["C:\\R\\Rscript.exe", "C:/scripts/test_script.R", "ext_par=99"]]


def test_run_streaming_calls_on_process_start_with_the_popen_instance(engine, fake_popen_killable):
    task = {
        "file_path": "C:\\scripts\\test_script.R",
        "config": [],
    }
    captured = []

    engine._execute_r_task(task, capture_output=True, on_output=lambda line: captured[0].terminate(),
                            on_process_start=captured.append)

    assert len(captured) == 1
    assert hasattr(captured[0], "terminate")  # it's the Popen (fake), not something else


def test_run_streaming_stops_cleanly_when_process_is_terminated_mid_stream(engine, fake_popen_killable):
    """A kill switch calls Popen.terminate() from elsewhere while _run_streaming is
    still reading lines. The read loop must stop and still return a normal
    ExecutionResult (not hang or raise) once the process is terminated."""
    task = {
        "file_path": "C:\\scripts\\test_script.R",
        "config": [],
    }
    received = []
    process_holder = []

    def on_output(line):
        received.append(line)
        if len(received) == 3:
            process_holder[0].terminate()  # simulate the kill switch firing mid-stream

    result = engine._execute_r_task(
        task, capture_output=True, on_output=on_output, on_process_start=process_holder.append
    )

    assert received == ["line1", "line2", "line3"]  # stopped right after terminate()
    assert isinstance(result, ExecutionResult)
    assert result.returncode == 1  # whatever the (fake) terminated process reports


def test_capture_output_without_on_output_still_uses_blocking_subprocess_run(engine, fake_run, fake_popen):
    """When capture_output=True but no on_output callback is given, fall back to the
    original blocking subprocess.run path rather than streaming -- Popen must not be used."""
    task = {
        "file_path": "C:\\scripts\\test_script.R",
        "config": [{"script_name": "ext_par", "script_value": "5"}],
    }

    result = engine._execute_r_task(task, capture_output=True)

    assert result.stdout == "hello output"
    assert fake_popen == []  # Popen (streaming) was never invoked
