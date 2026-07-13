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
