import json
import logging

from classes.Parser import Parser


def write(folder, filename, content):
    path = folder / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def write_task(folder, name="1_task", module="test_module"):
    content = (
        f'#@MODELFLOW_task name="{name}" module="{module}"\n'
        '#@MODELFLOW_config name="ext_par" type="number" role="parameter"\n'
        "ext_par = 5\n"
    )
    write(folder, "script_" + name + ".R", content=content)


def write_pipelines_file(folder, module, pipelines, filename="model_flow.pipelines.json"):
    write(folder, filename, content=json.dumps({"module": module, "pipelines": pipelines}))


def test_parse_pipelines_returns_empty_dict_when_no_pipelines_files(tmp_path):
    write_task(tmp_path, name="1_task")
    modules = Parser.parse_modules(str(tmp_path))

    assert Parser.parse_pipelines(str(tmp_path), modules) == {}


def test_parse_pipelines_discovers_valid_pipeline_file(tmp_path):
    write_task(tmp_path, name="1_task")
    write_task(tmp_path, name="2_task")
    write_pipelines_file(tmp_path, "test_module", [
        {"name": "run_all", "description": "Runs everything.", "tasks": ["1_task", "2_task"]},
    ])

    modules = Parser.parse_modules(str(tmp_path))
    pipelines = Parser.parse_pipelines(str(tmp_path), modules)

    assert pipelines == {
        "test_module": [
            {"name": "run_all", "description": "Runs everything.", "tasks": ["1_task", "2_task"]},
        ]
    }


def test_parse_pipelines_skips_file_with_missing_module_field(tmp_path, caplog):
    write_task(tmp_path, name="1_task")
    write(tmp_path, "model_flow.pipelines.json", content=json.dumps({
        "pipelines": [{"name": "run_all", "tasks": ["1_task"]}]
    }))

    modules = Parser.parse_modules(str(tmp_path))
    with caplog.at_level(logging.WARNING):
        pipelines = Parser.parse_pipelines(str(tmp_path), modules)

    assert pipelines == {}
    assert "missing" in caplog.text.lower()


def test_parse_pipelines_skips_pipeline_referencing_unknown_task(tmp_path):
    write_task(tmp_path, name="1_task")
    write_pipelines_file(tmp_path, "test_module", [
        {"name": "bad", "tasks": ["1_task", "does_not_exist"]},
        {"name": "good", "tasks": ["1_task"]},
    ])

    modules = Parser.parse_modules(str(tmp_path))
    pipelines = Parser.parse_pipelines(str(tmp_path), modules)

    assert pipelines == {
        "test_module": [
            {"name": "good", "description": "", "tasks": ["1_task"]},
        ]
    }


def test_parse_pipelines_skips_pipeline_with_empty_or_malformed_tasks_list(tmp_path):
    write_task(tmp_path, name="1_task")
    write_pipelines_file(tmp_path, "test_module", [
        {"name": "empty", "tasks": []},
        {"name": "malformed", "tasks": "1_task"},
        {"name": "good", "tasks": ["1_task"]},
    ])

    modules = Parser.parse_modules(str(tmp_path))
    pipelines = Parser.parse_pipelines(str(tmp_path), modules)

    assert pipelines == {
        "test_module": [
            {"name": "good", "description": "", "tasks": ["1_task"]},
        ]
    }


def test_parse_pipelines_skips_duplicate_pipeline_name_within_module(tmp_path):
    write_task(tmp_path, name="1_task")
    write_pipelines_file(tmp_path, "test_module", [
        {"name": "run_all", "tasks": ["1_task"]},
        {"name": "run_all", "tasks": ["1_task"]},
    ])

    modules = Parser.parse_modules(str(tmp_path))
    pipelines = Parser.parse_pipelines(str(tmp_path), modules)

    assert len(pipelines["test_module"]) == 1


def test_parse_pipelines_catches_duplicate_names_across_folders_for_same_module(tmp_path):
    write_task(tmp_path / "a", name="1_task", module="shared_module")
    write_task(tmp_path / "b", name="2_task", module="shared_module")
    write_pipelines_file(tmp_path / "a", "shared_module", [{"name": "run_all", "tasks": ["1_task"]}])
    write_pipelines_file(tmp_path / "b", "shared_module", [{"name": "run_all", "tasks": ["2_task"]}])

    modules = Parser.parse_modules(str(tmp_path))
    pipelines = Parser.parse_pipelines(str(tmp_path), modules)

    # first-seen wins; os.walk's traversal order across sibling folders isn't
    # guaranteed, so only assert dedup happened, not which folder "won".
    assert len(pipelines["shared_module"]) == 1
    assert pipelines["shared_module"][0]["tasks"] in (["1_task"], ["2_task"])


def test_parse_pipelines_skips_malformed_json_without_aborting_walk(tmp_path):
    write_task(tmp_path / "a", name="1_task")
    write_task(tmp_path / "b", name="2_task")
    write(tmp_path / "a", "model_flow.pipelines.json", content="{not valid json")
    write_pipelines_file(tmp_path / "b", "test_module", [{"name": "run_all", "tasks": ["2_task"]}])

    modules = Parser.parse_modules(str(tmp_path))
    pipelines = Parser.parse_pipelines(str(tmp_path), modules)

    assert pipelines == {
        "test_module": [
            {"name": "run_all", "description": "", "tasks": ["2_task"]},
        ]
    }
