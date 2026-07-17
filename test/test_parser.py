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


def write_lists_file(folder, lists, filename="model_flow.lists.json"):
    write(folder, filename, content=json.dumps({"lists": lists}))


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
            {"name": "run_all", "description": "Runs everything.", "tasks": [
                {"task": "1_task", "overrides": {}, "loop": None},
                {"task": "2_task", "overrides": {}, "loop": None},
            ]},
        ]
    }


def test_parse_pipelines_normalizes_object_task_entry_with_overrides(tmp_path):
    write_task(tmp_path, name="1_task")
    write_pipelines_file(tmp_path, "test_module", [
        {"name": "run_all", "tasks": [{"task": "1_task", "overrides": {"ext_par": "7"}}]},
    ])

    modules = Parser.parse_modules(str(tmp_path))
    pipelines = Parser.parse_pipelines(str(tmp_path), modules)

    assert pipelines["test_module"][0]["tasks"] == [
        {"task": "1_task", "overrides": {"ext_par": "7"}, "loop": None},
    ]


def test_parse_pipelines_skips_pipeline_with_unknown_override_parameter(tmp_path):
    write_task(tmp_path, name="1_task")
    write_pipelines_file(tmp_path, "test_module", [
        {"name": "bad", "tasks": [{"task": "1_task", "overrides": {"does_not_exist": "1"}}]},
        {"name": "good", "tasks": ["1_task"]},
    ])

    modules = Parser.parse_modules(str(tmp_path))
    pipelines = Parser.parse_pipelines(str(tmp_path), modules)

    assert [p["name"] for p in pipelines["test_module"]] == ["good"]


def test_parse_pipelines_normalizes_single_parameter_loop(tmp_path):
    write_task(tmp_path, name="1_task")
    write_pipelines_file(tmp_path, "test_module", [
        {"name": "run_all", "tasks": [
            {"task": "1_task", "loop": {"parameters": {"ext_par": "nuts2"}, "mode": "parallel"}},
        ]},
    ])

    modules = Parser.parse_modules(str(tmp_path))
    lists = {"nuts2": {"name": "nuts2", "elements": ["AT11", "AT12"]}}
    pipelines = Parser.parse_pipelines(str(tmp_path), modules, lists)

    assert pipelines["test_module"][0]["tasks"] == [
        {"task": "1_task", "overrides": {}, "loop": {
            "parameters": {"ext_par": "nuts2"}, "combine": None, "mode": "parallel", "max_workers": None,
        }},
    ]


def test_parse_pipelines_accepts_zip_loop_with_equal_length_lists(tmp_path):
    content = (
        '#@MODELFLOW_task name="1_task" module="test_module"\n'
        '#@MODELFLOW_config name="a" type="string" role="parameter"\n'
        'a = "x",\n'
        '#@MODELFLOW_config name="b" type="string" role="parameter"\n'
        'b = "y",\n'
    )
    write(tmp_path, "script_1_task.R", content=content)
    write_pipelines_file(tmp_path, "test_module", [
        {"name": "run_all", "tasks": [
            {"task": "1_task", "loop": {"parameters": {"a": "list_a", "b": "list_b"}, "combine": "zip"}},
        ]},
    ])

    modules = Parser.parse_modules(str(tmp_path))
    lists = {
        "list_a": {"name": "list_a", "elements": ["1", "2"]},
        "list_b": {"name": "list_b", "elements": ["3", "4"]},
    }
    pipelines = Parser.parse_pipelines(str(tmp_path), modules, lists)

    assert pipelines["test_module"][0]["tasks"][0]["loop"]["combine"] == "zip"


def test_parse_pipelines_skips_zip_loop_with_mismatched_list_lengths(tmp_path):
    content = (
        '#@MODELFLOW_task name="1_task" module="test_module"\n'
        '#@MODELFLOW_config name="a" type="string" role="parameter"\n'
        'a = "x",\n'
        '#@MODELFLOW_config name="b" type="string" role="parameter"\n'
        'b = "y",\n'
    )
    write(tmp_path, "script_1_task.R", content=content)
    write_pipelines_file(tmp_path, "test_module", [
        {"name": "bad", "tasks": [
            {"task": "1_task", "loop": {"parameters": {"a": "list_a", "b": "list_b"}, "combine": "zip"}},
        ]},
        {"name": "good", "tasks": ["1_task"]},
    ])

    modules = Parser.parse_modules(str(tmp_path))
    lists = {
        "list_a": {"name": "list_a", "elements": ["1", "2"]},
        "list_b": {"name": "list_b", "elements": ["3"]},
    }
    pipelines = Parser.parse_pipelines(str(tmp_path), modules, lists)

    assert [p["name"] for p in pipelines["test_module"]] == ["good"]


def test_parse_pipelines_skips_multi_parameter_loop_missing_combine(tmp_path):
    content = (
        '#@MODELFLOW_task name="1_task" module="test_module"\n'
        '#@MODELFLOW_config name="a" type="string" role="parameter"\n'
        'a = "x",\n'
        '#@MODELFLOW_config name="b" type="string" role="parameter"\n'
        'b = "y",\n'
    )
    write(tmp_path, "script_1_task.R", content=content)
    write_pipelines_file(tmp_path, "test_module", [
        {"name": "bad", "tasks": [
            {"task": "1_task", "loop": {"parameters": {"a": "list_a", "b": "list_b"}}},
        ]},
        {"name": "good", "tasks": ["1_task"]},
    ])

    modules = Parser.parse_modules(str(tmp_path))
    lists = {
        "list_a": {"name": "list_a", "elements": ["1"]},
        "list_b": {"name": "list_b", "elements": ["1"]},
    }
    pipelines = Parser.parse_pipelines(str(tmp_path), modules, lists)

    assert [p["name"] for p in pipelines["test_module"]] == ["good"]


def test_parse_pipelines_skips_loop_referencing_unknown_list(tmp_path):
    write_task(tmp_path, name="1_task")
    write_pipelines_file(tmp_path, "test_module", [
        {"name": "bad", "tasks": [{"task": "1_task", "loop": {"parameters": {"ext_par": "does_not_exist"}}}]},
        {"name": "good", "tasks": ["1_task"]},
    ])

    modules = Parser.parse_modules(str(tmp_path))
    pipelines = Parser.parse_pipelines(str(tmp_path), modules, {})

    assert [p["name"] for p in pipelines["test_module"]] == ["good"]


def test_parse_pipelines_skips_loop_parameter_overlapping_overrides(tmp_path):
    write_task(tmp_path, name="1_task")
    write_pipelines_file(tmp_path, "test_module", [
        {"name": "bad", "tasks": [{
            "task": "1_task",
            "overrides": {"ext_par": "1"},
            "loop": {"parameters": {"ext_par": "nuts2"}},
        }]},
        {"name": "good", "tasks": ["1_task"]},
    ])

    modules = Parser.parse_modules(str(tmp_path))
    lists = {"nuts2": {"name": "nuts2", "elements": ["AT11"]}}
    pipelines = Parser.parse_pipelines(str(tmp_path), modules, lists)

    assert [p["name"] for p in pipelines["test_module"]] == ["good"]


def test_parse_pipelines_skips_loop_with_invalid_mode(tmp_path):
    write_task(tmp_path, name="1_task")
    write_pipelines_file(tmp_path, "test_module", [
        {"name": "bad", "tasks": [
            {"task": "1_task", "loop": {"parameters": {"ext_par": "nuts2"}, "mode": "concurrently"}},
        ]},
        {"name": "good", "tasks": ["1_task"]},
    ])

    modules = Parser.parse_modules(str(tmp_path))
    lists = {"nuts2": {"name": "nuts2", "elements": ["AT11"]}}
    pipelines = Parser.parse_pipelines(str(tmp_path), modules, lists)

    assert [p["name"] for p in pipelines["test_module"]] == ["good"]


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
            {"name": "good", "description": "", "tasks": [{"task": "1_task", "overrides": {}, "loop": None}]},
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
            {"name": "good", "description": "", "tasks": [{"task": "1_task", "overrides": {}, "loop": None}]},
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
    assert pipelines["shared_module"][0]["tasks"] in (
        [{"task": "1_task", "overrides": {}, "loop": None}],
        [{"task": "2_task", "overrides": {}, "loop": None}],
    )


def test_parse_pipelines_skips_malformed_json_without_aborting_walk(tmp_path):
    write_task(tmp_path / "a", name="1_task")
    write_task(tmp_path / "b", name="2_task")
    write(tmp_path / "a", "model_flow.pipelines.json", content="{not valid json")
    write_pipelines_file(tmp_path / "b", "test_module", [{"name": "run_all", "tasks": ["2_task"]}])

    modules = Parser.parse_modules(str(tmp_path))
    pipelines = Parser.parse_pipelines(str(tmp_path), modules)

    assert pipelines == {
        "test_module": [
            {"name": "run_all", "description": "", "tasks": [{"task": "2_task", "overrides": {}, "loop": None}]},
        ]
    }


def test_parse_lists_returns_empty_dict_when_no_lists_files(tmp_path):
    assert Parser.parse_lists(str(tmp_path)) == {}


def test_parse_lists_discovers_list_file_at_root_with_folder_dot(tmp_path):
    write_lists_file(tmp_path, [{"name": "nuts0", "type": "string", "elements": ["AT", "BE"]}])

    lists = Parser.parse_lists(str(tmp_path))

    assert lists == {
        "nuts0": {"name": "nuts0", "type": "string", "elements": ["AT", "BE"], "folder": "."},
    }


def test_parse_lists_discovers_list_file_in_nested_folder_with_relative_path(tmp_path):
    write_lists_file(tmp_path / "v.main2020" / "d.policy", [
        {"name": "nuts2", "type": "string", "elements": ["AT11", "AT12"]},
    ])

    lists = Parser.parse_lists(str(tmp_path))

    assert lists["nuts2"]["folder"] == "v.main2020/d.policy"
    assert lists["nuts2"]["elements"] == ["AT11", "AT12"]


def test_parse_lists_collects_from_multiple_folders(tmp_path):
    write_lists_file(tmp_path / "a", [{"name": "list_a", "elements": ["1"]}])
    write_lists_file(tmp_path / "b", [{"name": "list_b", "elements": ["2"]}])

    lists = Parser.parse_lists(str(tmp_path))

    assert set(lists.keys()) == {"list_a", "list_b"}
    assert lists["list_a"]["folder"] == "a"
    assert lists["list_b"]["folder"] == "b"


def test_parse_lists_skips_unnamed_list(tmp_path, caplog):
    write_lists_file(tmp_path, [{"elements": ["AT"]}])

    with caplog.at_level(logging.WARNING):
        lists = Parser.parse_lists(str(tmp_path))

    assert lists == {}
    assert "unnamed" in caplog.text.lower()


def test_parse_lists_skips_duplicate_name_across_folders(tmp_path, caplog):
    write_lists_file(tmp_path / "a", [{"name": "nuts0", "elements": ["AT"]}])
    write_lists_file(tmp_path / "b", [{"name": "nuts0", "elements": ["BE"]}])

    with caplog.at_level(logging.WARNING):
        lists = Parser.parse_lists(str(tmp_path))

    # first-seen wins; os.walk's traversal order across sibling folders isn't
    # guaranteed, so only assert dedup happened, not which folder "won".
    assert len(lists) == 1
    assert lists["nuts0"]["elements"] in (["AT"], ["BE"])
    assert "duplicate" in caplog.text.lower()


def test_parse_lists_skips_malformed_json_without_aborting_walk(tmp_path):
    write(tmp_path / "a", "model_flow.lists.json", content="{not valid json")
    write_lists_file(tmp_path / "b", [{"name": "nuts0", "elements": ["AT"]}])

    lists = Parser.parse_lists(str(tmp_path))

    assert lists == {
        "nuts0": {"name": "nuts0", "elements": ["AT"], "folder": "b"},
    }


def test_parse_lists_on_file_callback_invoked_per_lists_file(tmp_path):
    write_lists_file(tmp_path / "a", [{"name": "list_a", "elements": ["1"]}])
    write_lists_file(tmp_path / "b", [{"name": "list_b", "elements": ["2"]}])

    seen = []
    Parser.parse_lists(str(tmp_path), on_file=seen.append)

    assert len(seen) == 2


def test_expand_loop_single_parameter_iterates_list_elements():
    loop = {"parameters": {"nuts_code": "nuts2"}}
    resolve = {"nuts2": ["AT11", "AT12", "AT13"]}.get

    assert Parser.expand_loop(loop, resolve) == [
        {"nuts_code": "AT11"}, {"nuts_code": "AT12"}, {"nuts_code": "AT13"},
    ]


def test_expand_loop_zip_combines_lists_pairwise():
    loop = {"parameters": {"region_from": "list_a", "region_to": "list_b"}, "combine": "zip"}
    resolve = {"list_a": ["AT11", "AT12"], "list_b": ["BE10", "BE21"]}.get

    assert Parser.expand_loop(loop, resolve) == [
        {"region_from": "AT11", "region_to": "BE10"},
        {"region_from": "AT12", "region_to": "BE21"},
    ]


def test_expand_loop_product_combines_all_pairs():
    loop = {"parameters": {"region_from": "list_a", "region_to": "list_b"}, "combine": "product"}
    resolve = {"list_a": ["AT11", "AT12"], "list_b": ["BE10", "BE21"]}.get

    assert Parser.expand_loop(loop, resolve) == [
        {"region_from": "AT11", "region_to": "BE10"},
        {"region_from": "AT11", "region_to": "BE21"},
        {"region_from": "AT12", "region_to": "BE10"},
        {"region_from": "AT12", "region_to": "BE21"},
    ]
