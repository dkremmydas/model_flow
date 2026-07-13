import json
from unittest.mock import patch

import pytest
from textual.widgets import Tree

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
        task_node = select_task.tree.root.children[0].children[0]
        await select_task_node(pilot, select_task, task_node)

        show_task = app.query_one(ShowTask)
        assert show_task.current_task["name"] == "1_test_task"

        input_widget = app.query_one("#input-ext_par")
        assert input_widget.value == "5"
        assert show_task.get_overrides() == {}

        input_widget.value = "99"
        await pilot.pause()
        assert show_task.get_overrides() == {"ext_par": "99"}


async def test_execute_task_calls_engine_with_overrides_and_persists_history(tmp_path):
    write_db_with_one_task(tmp_path)
    app = ModelFlowApp(make_config(tmp_path))

    async with app.run_test() as pilot:
        select_task = app.query_one(SelectTask)
        task_node = select_task.tree.root.children[0].children[0]
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
            "test_module", "1_test_task", None, {"ext_par": "99"}, True
        )

        execute_panel = app.query_one(ExecuteTask)
        assert "succeeded" in str(execute_panel.status.content)

        user_db_path = tmp_path / "model_flow.db_user.json"
        assert user_db_path.exists()
        user_data = json.loads(user_db_path.read_text(encoding="utf-8"))
        assert user_data["test_module"][0]["config"][0]["script_value"] == ["99"]

        # Re-selecting the task should now offer the recorded value as a history option.
        await select_task_node(pilot, select_task, task_node)
        assert app.query_one("#select-ext_par") is not None


async def test_execute_task_shows_error_status_on_engine_failure(tmp_path):
    write_db_with_one_task(tmp_path)
    app = ModelFlowApp(make_config(tmp_path))

    async with app.run_test() as pilot:
        select_task = app.query_one(SelectTask)
        task_node = select_task.tree.root.children[0].children[0]
        await select_task_node(pilot, select_task, task_node)

        with patch.object(app.engine, "execute_task", side_effect=RuntimeError("boom")):
            await app.action_execute_task()
            await pilot.pause()

        execute_panel = app.query_one(ExecuteTask)
        assert "failed to start" in str(execute_panel.status.content)
