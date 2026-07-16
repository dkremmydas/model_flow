import asyncio
import json
import threading
from unittest.mock import ANY, patch

import pytest
from textual.widgets import Input, Tree

from classes.Config import Config
from classes.ExecutionEngine import ExecutionResult
from textual_gui.app import ExecuteTask, ModelFlowApp, ShowTask, SelectTask

pytestmark = pytest.mark.asyncio


async def select_task_node(pilot, select_task_widget, task_node):
    """Simulate a real user selecting a tree node the way a click/Enter would:
    post the actual Tree.NodeSelected message rather than calling
    ModelFlowApp.select_task directly, so the on_tree_node_selected handler
    (and whether it actually awaits the coroutine) is exercised for real."""
    select_task_widget.tree.post_message(Tree.NodeSelected(task_node))
    await pilot.pause()


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


def write_db_with_one_task_and_pipeline(tmp_path):
    write_db_with_one_task(tmp_path)
    pipelines_content = {
        "test_module": [
            {
                "name": "full_run",
                "description": "Runs everything.",
                "tasks": ["1_test_task"],
            }
        ]
    }
    (tmp_path / "model_flow.pipelines.json").write_text(json.dumps(pipelines_content), encoding="utf-8")


async def test_missing_database_shows_friendly_message(tmp_path):
    app = ModelFlowApp(make_config(tmp_path))  # no model_flow.db.json written

    assert app.startup_error is not None
    assert app.database is None

    async with app.run_test() as pilot:
        error_widget = app.query_one("#startup-error")
        assert "build" in str(error_widget.content)


async def test_tree_populated_from_database_and_search_filters_it(tmp_path):
    write_db_with_one_task(tmp_path)
    app = ModelFlowApp(make_config(tmp_path))
    assert app.startup_error is None

    async with app.run_test() as pilot:
        select_task = app.query_one(SelectTask)
        assert select_task.module_tasks["test_module"] == ["1_test_task"]

        search_input = app.query_one("#module-search")

        search_input.value = "nonexistent"
        await pilot.pause()
        assert list(select_task.tree.root.children) == []

        search_input.value = "test_task"
        await pilot.pause()
        assert len(list(select_task.tree.root.children)) == 1


async def test_selecting_task_populates_editable_config_with_default_value(tmp_path):
    write_db_with_one_task(tmp_path)
    app = ModelFlowApp(make_config(tmp_path))

    async with app.run_test() as pilot:
        select_task = app.query_one(SelectTask)
        task_node = select_task.tree.root.children[0].children[0].children[0]
        await select_task_node(pilot, select_task, task_node)

        show_task = app.query_one(ShowTask)
        assert show_task.current_task["name"] == "1_test_task"

        input_widget = app.query_one("#input-ext_par")
        assert input_widget.value == "5"
        assert show_task.get_overrides() == {}

        input_widget.value = "99"
        await pilot.pause()
        assert show_task.get_overrides() == {"ext_par": "99"}


async def test_selecting_pipeline_shows_its_tasks_in_right_panel(tmp_path):
    write_db_with_one_task_and_pipeline(tmp_path)
    app = ModelFlowApp(make_config(tmp_path))

    async with app.run_test() as pilot:
        select_task = app.query_one(SelectTask)
        assert select_task.module_pipelines["test_module"] == ["full_run"]

        module_node = select_task.tree.root.children[0]
        pipelines_node = module_node.children[1]  # ["Tasks", "Pipelines"][1]
        assert str(pipelines_node.label) == "Pipelines"
        pipeline_node = pipelines_node.children[0]
        await select_task_node(pilot, select_task, pipeline_node)

        show_task = app.query_one(ShowTask)
        assert show_task.current_task is None  # not an editable/runnable task
        assert app.selected_task is None  # ctrl+r must not run a stale task selection

        tree_labels = [str(n.label) for n in show_task.task_tree.root.children]
        assert any("tasks" in label for label in tree_labels)
        assert "1_test_task" in str(app.query_one(ShowTask).task_tree.root.children[-1].children[0].label)

        assert "Runs everything." in show_task.description_log.lines


async def test_editing_pipeline_task_param_persists_to_db_user_json_on_submit(tmp_path):
    write_db_with_one_task_and_pipeline(tmp_path)
    app = ModelFlowApp(make_config(tmp_path))
    user_db_path = tmp_path / "model_flow.db_user.json"

    async with app.run_test() as pilot:
        select_task = app.query_one(SelectTask)
        pipeline_node = select_task.tree.root.children[0].children[1].children[0]
        await select_task_node(pilot, select_task, pipeline_node)

        input_widget = app.query_one("#input-pipeline-1_test_task_ext_par", Input)
        assert input_widget.value == "5"

        # Typing alone (Input.Changed) must not persist -- only a committed edit should.
        input_widget.value = "42"
        await pilot.pause()
        assert not user_db_path.exists()

        input_widget.post_message(Input.Submitted(input_widget, "42"))
        await pilot.pause()

        assert user_db_path.exists()
        user_data = json.loads(user_db_path.read_text(encoding="utf-8"))
        assert user_data["test_module"][0]["name"] == "1_test_task"
        assert user_data["test_module"][0]["config"][0]["script_value"] == ["42"]

        # Re-submitting the same (default) value is not a change -- nothing new recorded.
        input_widget.value = "5"
        input_widget.post_message(Input.Submitted(input_widget, "5"))
        await pilot.pause()
        user_data = json.loads(user_db_path.read_text(encoding="utf-8"))
        assert user_data["test_module"][0]["config"][0]["script_value"] == ["42"]


async def test_execute_task_calls_engine_with_overrides_and_persists_history(tmp_path):
    write_db_with_one_task(tmp_path)
    app = ModelFlowApp(make_config(tmp_path))

    async with app.run_test() as pilot:
        select_task = app.query_one(SelectTask)
        task_node = select_task.tree.root.children[0].children[0].children[0]
        await select_task_node(pilot, select_task, task_node)

        input_widget = app.query_one("#input-ext_par")
        input_widget.value = "99"
        await pilot.pause()

        with patch.object(
            app.engine, "execute_task",
            return_value=ExecutionResult(returncode=0, stdout="ran ok", stderr=""),
        ) as mock_execute:
            await app.action_execute_task()
            await pilot.pause()

        mock_execute.assert_called_once_with(
            "test_module", "1_test_task", None, {"ext_par": "99"}, True, ANY, ANY
        )
        on_output, on_process_start = mock_execute.call_args.args[5:7]
        assert callable(on_output)
        assert callable(on_process_start)

        execute_panel = app.query_one(ExecuteTask)
        assert "succeeded" in str(execute_panel.status.content)

        user_db_path = tmp_path / "model_flow.db_user.json"
        assert user_db_path.exists()
        user_data = json.loads(user_db_path.read_text(encoding="utf-8"))
        assert user_data["test_module"][0]["config"][0]["script_value"] == ["99"]

        # Re-selecting the task should now offer the recorded value as a history option.
        await select_task_node(pilot, select_task, task_node)
        assert app.query_one("#select-ext_par") is not None


async def test_execute_task_streams_output_live_via_call_from_thread(tmp_path):
    """The on_output callback passed to ExecutionEngine.execute_task runs on a real
    worker thread (via asyncio.to_thread) in production. Exercise that for real here
    rather than calling it directly, since App.call_from_thread raises if invoked
    from the app's own thread -- calling it wrong wouldn't be caught otherwise."""
    write_db_with_one_task(tmp_path)
    app = ModelFlowApp(make_config(tmp_path))

    async with app.run_test() as pilot:
        select_task = app.query_one(SelectTask)
        task_node = select_task.tree.root.children[0].children[0].children[0]
        await select_task_node(pilot, select_task, task_node)

        def fake_execute_task(module, task_name, output_dir, overrides, capture_output, on_output, on_process_start):
            on_output("streaming line 1")
            on_output("streaming line 2")
            return ExecutionResult(returncode=0, stdout="streaming line 1\nstreaming line 2", stderr="")

        with patch.object(app.engine, "execute_task", side_effect=fake_execute_task):
            await app.action_execute_task()
            await pilot.pause()

        execute_panel = app.query_one(ExecuteTask)
        assert list(execute_panel.output_log.lines) == [
            "streaming line 1",
            "streaming line 2",
            "Task test_module/1_test_task, finished",
        ]
        assert "succeeded" in str(execute_panel.status.content)


async def test_kill_task_terminates_running_process_and_shows_aborted(tmp_path):
    """action_kill_task must actually reach the running Popen and terminate() it,
    and the run must then report as 'aborted' rather than succeeded/failed. Uses a
    real background thread (like production's asyncio.to_thread) so the process is
    genuinely still 'running' when ctrl+k fires, not already finished."""
    write_db_with_one_task(tmp_path)
    app = ModelFlowApp(make_config(tmp_path))

    class FakeProcess:
        def __init__(self):
            self.terminated = threading.Event()

        def poll(self):
            return None if not self.terminated.is_set() else 1

        def terminate(self):
            self.terminated.set()

    fake_process = FakeProcess()

    def fake_execute_task(module, task_name, output_dir, overrides, capture_output, on_output, on_process_start):
        on_process_start(fake_process)
        fake_process.terminated.wait(timeout=5)  # blocks here until action_kill_task() terminates it
        return ExecutionResult(returncode=1, stdout="", stderr="")

    async with app.run_test() as pilot:
        select_task = app.query_one(SelectTask)
        task_node = select_task.tree.root.children[0].children[0].children[0]
        await select_task_node(pilot, select_task, task_node)

        with patch.object(app.engine, "execute_task", side_effect=fake_execute_task):
            run_task = asyncio.ensure_future(app.action_execute_task())
            await asyncio.sleep(0.2)  # let the worker thread reach on_process_start and block

            assert app.current_process is fake_process
            app.action_kill_task()
            assert app.execution_cancelled is True

            await run_task
            await pilot.pause()

        assert fake_process.terminated.is_set()
        assert app.current_process is None

        execute_panel = app.query_one(ExecuteTask)
        assert "aborted" in str(execute_panel.status.content)
        assert execute_panel.output_log.lines[-1] == "Task test_module/1_test_task, aborted"


async def test_kill_task_does_nothing_when_no_task_is_running(tmp_path):
    write_db_with_one_task(tmp_path)
    app = ModelFlowApp(make_config(tmp_path))

    async with app.run_test() as pilot:
        app.action_kill_task()  # must not raise
        assert app.execution_cancelled is False


async def test_execute_task_ignores_second_press_while_already_running(tmp_path):
    write_db_with_one_task(tmp_path)
    app = ModelFlowApp(make_config(tmp_path))

    class FakeProcess:
        def poll(self):
            return None  # still running

    def fake_execute_task(module, task_name, output_dir, overrides, capture_output, on_output, on_process_start):
        on_process_start(FakeProcess())
        raise AssertionError("should not be called a second time while a run is in progress")

    async with app.run_test() as pilot:
        select_task = app.query_one(SelectTask)
        task_node = select_task.tree.root.children[0].children[0].children[0]
        await select_task_node(pilot, select_task, task_node)

        app.current_process = FakeProcess()  # simulate a run already in progress

        with patch.object(app.engine, "execute_task", side_effect=fake_execute_task):
            await app.action_execute_task()  # should return immediately, not call execute_task


async def test_execute_task_panel_sub_title_toggles_with_run_lifecycle(tmp_path):
    write_db_with_one_task(tmp_path)
    app = ModelFlowApp(make_config(tmp_path))

    async with app.run_test() as pilot:
        execute_panel = app.query_one(ExecuteTask)
        assert app.sub_title == ""

        execute_panel.start_running("Running test_module/1_test_task...")
        assert app.sub_title == "Running test_module/1_test_task..."

        execute_panel.show_result("test_module", "1_test_task", 0)
        assert app.sub_title == ""
        assert execute_panel.output_log.lines[-1] == "Task test_module/1_test_task, finished"

        execute_panel.start_running("Running again...")
        assert app.sub_title == "Running again..."

        execute_panel.show_error("test_module", "1_test_task", "boom")
        assert app.sub_title == ""


async def test_sub_title_stays_visible_while_output_panel_is_toggled_off(tmp_path):
    """The header sub-title is the one status signal that survives ctrl+o, so it must
    still say 'Running...' even when the output panel itself is hidden in favor of
    the browse view."""
    write_db_with_one_task(tmp_path)
    app = ModelFlowApp(make_config(tmp_path))

    async with app.run_test() as pilot:
        execute_panel = app.query_one(ExecuteTask)

        # Mirror what action_execute_task does before calling start_running:
        # switch to the full-screen output view.
        execute_panel.display = True
        app.main_view.display = False
        execute_panel.start_running("Running test_module/1_test_task...")
        assert app.sub_title == "Running test_module/1_test_task..."

        await pilot.press("ctrl+o")  # switch back to browsing mid-run
        assert execute_panel.display is False
        assert app.main_view.display is True
        assert app.sub_title == "Running test_module/1_test_task..."  # still visible

        execute_panel.show_result("test_module", "1_test_task", 0)
        assert app.sub_title == ""


async def test_toggle_output_binding_switches_between_fullscreen_and_hidden(tmp_path):
    write_db_with_one_task(tmp_path)
    app = ModelFlowApp(make_config(tmp_path))

    async with app.run_test() as pilot:
        execute_panel = app.query_one(ExecuteTask)
        main_view = app.main_view
        assert execute_panel.display is False
        assert main_view.display is True

        await pilot.press("ctrl+o")
        assert execute_panel.display is True
        assert main_view.display is False

        await pilot.press("ctrl+o")
        assert execute_panel.display is False
        assert main_view.display is True


async def test_execute_task_reveals_hidden_output_panel_fullscreen(tmp_path):
    write_db_with_one_task(tmp_path)
    app = ModelFlowApp(make_config(tmp_path))

    async with app.run_test() as pilot:
        select_task = app.query_one(SelectTask)
        task_node = select_task.tree.root.children[0].children[0].children[0]
        await select_task_node(pilot, select_task, task_node)

        execute_panel = app.query_one(ExecuteTask)
        assert execute_panel.display is False

        with patch.object(
            app.engine, "execute_task",
            return_value=ExecutionResult(returncode=0, stdout="ran ok", stderr=""),
        ):
            await app.action_execute_task()
            await pilot.pause()

        assert execute_panel.display is True
        assert app.main_view.display is False


async def test_rebuild_database_binding_rescans_code_directory(tmp_path):
    write_db_with_one_task(tmp_path)
    app = ModelFlowApp(make_config(tmp_path))

    # A new task script appears in Code_directory after the app has already started.
    new_script = tmp_path / "new_script.R"
    new_script.write_text(
        '#@MODELFLOW_task name="2_new_task" module="new_module"\n'
        'x <- 1\n',
        encoding="utf-8",
    )

    async with app.run_test() as pilot:
        select_task = app.query_one(SelectTask)
        assert "new_module" not in select_task.modules

        await pilot.press("ctrl+b")
        await pilot.pause()

        assert "new_module" in select_task.modules
        assert select_task.module_tasks["new_module"] == ["2_new_task"]

        execute_panel = app.query_one(ExecuteTask)
        assert execute_panel.display is True
        assert app.main_view.display is False
        assert "modules" in str(execute_panel.status.content)
        assert app.sub_title == ""

        db_content = json.loads((tmp_path / "model_flow.db.json").read_text(encoding="utf-8"))
        assert "new_module" in db_content

        # The ExecutionEngine's own (separate) Database instance must see the new task too.
        assert app.engine.database.get_task("new_module", "2_new_task") is not None


async def test_execute_task_shows_error_status_on_engine_failure(tmp_path):
    write_db_with_one_task(tmp_path)
    app = ModelFlowApp(make_config(tmp_path))

    async with app.run_test() as pilot:
        select_task = app.query_one(SelectTask)
        task_node = select_task.tree.root.children[0].children[0].children[0]
        await select_task_node(pilot, select_task, task_node)

        with patch.object(app.engine, "execute_task", side_effect=RuntimeError("boom")):
            await app.action_execute_task()
            await pilot.pause()

        execute_panel = app.query_one(ExecuteTask)
        assert "failed to start" in str(execute_panel.status.content)
        assert app.sub_title == ""
