import json

from classes.Config import Config
from classes.Database import Database


def make_database(tmp_path) -> Database:
    (tmp_path / "model_flow.db.json").write_text("{}", encoding="utf-8")
    config_data = {
        "Code_directory": str(tmp_path),
        "Database_directory": str(tmp_path),
        "Temporary_directory": str(tmp_path),
        "Rscript_exe": "C:/R/Rscript.exe",
        "GAMS_exe": "C:/GAMS/gams.exe",
    }
    return Database(Config(json.dumps(config_data)))


def test_get_user_values_returns_empty_dict_when_no_user_db_file(tmp_path):
    database = make_database(tmp_path)

    assert database.get_user_values("test_module", "1_test_task") == {}


def test_add_user_value_then_get_user_values_round_trips(tmp_path):
    database = make_database(tmp_path)

    database.add_user_value("test_module", "1_test_task", "ext_par", "5")
    database.add_user_value("test_module", "1_test_task", "ext_par", "10")

    assert database.get_user_values("test_module", "1_test_task") == {"ext_par": ["5", "10"]}

    user_db_path = tmp_path / "model_flow.db_user.json"
    assert user_db_path.exists()
    on_disk = json.loads(user_db_path.read_text(encoding="utf-8"))
    assert on_disk["test_module"][0]["name"] == "1_test_task"


def test_add_user_value_does_not_duplicate_consecutive_identical_values(tmp_path):
    database = make_database(tmp_path)

    database.add_user_value("test_module", "1_test_task", "ext_par", "5")
    database.add_user_value("test_module", "1_test_task", "ext_par", "5")

    assert database.get_user_values("test_module", "1_test_task") == {"ext_par": ["5"]}


def test_add_user_value_is_isolated_per_task_and_module(tmp_path):
    database = make_database(tmp_path)

    database.add_user_value("module_a", "task_1", "param", "a-value")
    database.add_user_value("module_b", "task_1", "param", "b-value")

    assert database.get_user_values("module_a", "task_1") == {"param": ["a-value"]}
    assert database.get_user_values("module_b", "task_1") == {"param": ["b-value"]}


def test_user_db_is_loaded_by_a_fresh_database_instance(tmp_path):
    database = make_database(tmp_path)
    database.add_user_value("test_module", "1_test_task", "ext_par", "5")

    reloaded = make_database(tmp_path)

    assert reloaded.get_user_values("test_module", "1_test_task") == {"ext_par": ["5"]}


def test_list_and_get_pipelines_return_empty_when_no_pipelines_file(tmp_path):
    database = make_database(tmp_path)

    assert database.list_pipelines("test_module") == []
    assert database.get_pipeline("test_module", "run_all") is None


def test_add_pipeline_then_get_pipeline_round_trips(tmp_path):
    database = make_database(tmp_path)

    database.add_pipeline("test_module", {"name": "run_all", "description": "", "tasks": ["1_task", "2_task"]})

    assert database.get_pipeline("test_module", "run_all") == {
        "name": "run_all", "description": "", "tasks": ["1_task", "2_task"]
    }
    assert database.list_pipelines("test_module") == ["run_all"]


def test_add_pipeline_default_does_not_auto_persist(tmp_path):
    database = make_database(tmp_path)

    database.add_pipeline("test_module", {"name": "run_all", "tasks": ["1_task"]})

    assert not (tmp_path / "model_flow.pipelines.json").exists()

    database.save_pipelines()

    assert (tmp_path / "model_flow.pipelines.json").exists()
    on_disk = json.loads((tmp_path / "model_flow.pipelines.json").read_text(encoding="utf-8"))
    assert on_disk["test_module"][0]["name"] == "run_all"


def test_add_pipeline_user_true_persists_immediately(tmp_path):
    database = make_database(tmp_path)

    database.add_pipeline("test_module", {"name": "my_run", "tasks": ["1_task"]}, user=True)

    user_pipelines_path = tmp_path / "model_flow.pipelines_user.json"
    assert user_pipelines_path.exists()
    on_disk = json.loads(user_pipelines_path.read_text(encoding="utf-8"))
    assert on_disk["test_module"][0]["name"] == "my_run"


def test_get_pipeline_prefers_source_over_user_on_name_collision(tmp_path):
    database = make_database(tmp_path)

    database.add_pipeline("test_module", {"name": "run_all", "tasks": ["source_task"]}, user=False)
    database.add_pipeline("test_module", {"name": "run_all", "tasks": ["user_task"]}, user=True)

    assert database.get_pipeline("test_module", "run_all") == {"name": "run_all", "tasks": ["source_task"]}
    assert database.list_pipelines("test_module") == ["run_all"]  # deduped, not listed twice


def test_delete_pipeline_source_mutates_in_memory_only_until_save_pipelines_called(tmp_path):
    database = make_database(tmp_path)
    database.add_pipeline("test_module", {"name": "run_all", "tasks": ["1_task"]})
    database.save_pipelines()

    database.delete_pipeline("test_module", "run_all")

    assert database.get_pipeline("test_module", "run_all") is None
    on_disk = json.loads((tmp_path / "model_flow.pipelines.json").read_text(encoding="utf-8"))
    assert on_disk["test_module"][0]["name"] == "run_all"  # not yet saved

    database.save_pipelines()

    on_disk = json.loads((tmp_path / "model_flow.pipelines.json").read_text(encoding="utf-8"))
    assert on_disk["test_module"] == []


def test_user_pipelines_are_loaded_by_a_fresh_database_instance(tmp_path):
    database = make_database(tmp_path)
    database.add_pipeline("test_module", {"name": "my_run", "tasks": ["1_task"]}, user=True)

    reloaded = make_database(tmp_path)

    assert reloaded.get_pipeline("test_module", "my_run") == {"name": "my_run", "tasks": ["1_task"]}
