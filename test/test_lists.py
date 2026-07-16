import json

from classes.Config import Config
from classes.Lists import Lists


def make_lists(tmp_path, code_dir=None, db_dir=None) -> Lists:
    config_data = {
        "Code_directory": str(code_dir or tmp_path),
        "Database_directory": str(db_dir or tmp_path),
        "Temporary_directory": str(tmp_path),
        "Rscript_exe": "C:/R/Rscript.exe",
        "GAMS_exe": "C:/GAMS/gams.exe",
    }
    return Lists(Config(json.dumps(config_data)))


def test_list_names_and_get_list_return_empty_when_no_files_exist(tmp_path):
    lists = make_lists(tmp_path)

    assert lists.list_names() == []
    assert lists.get_list("nuts0") is None
    assert lists.get_elements("nuts0") is None


def test_reads_shared_lists_file_from_database_directory(tmp_path):
    code_dir = tmp_path / "code"
    db_dir = tmp_path / "db"
    code_dir.mkdir()
    db_dir.mkdir()

    # model_flow.lists.json here is the *build-generated* aggregate (from
    # Parser.parse_lists), so it's read from Database_directory, not Code_directory.
    (db_dir / "model_flow.lists.json").write_text(
        json.dumps({"lists": [{"name": "nuts0", "type": "string", "elements": ["AT", "BE"], "folder": "."}]}),
        encoding="utf-8",
    )

    lists = make_lists(tmp_path, code_dir=code_dir, db_dir=db_dir)

    assert lists.list_names() == ["nuts0"]
    assert lists.get_list("nuts0") == {
        "name": "nuts0", "type": "string", "elements": ["AT", "BE"], "folder": "."
    }
    assert lists.get_elements("nuts0") == ["AT", "BE"]


def test_reads_user_lists_file_from_database_directory(tmp_path):
    code_dir = tmp_path / "code"
    db_dir = tmp_path / "db"
    code_dir.mkdir()
    db_dir.mkdir()

    (db_dir / "model_flow.lists_user.json").write_text(
        json.dumps({"lists": [{"name": "my_list", "type": "number", "elements": [1, 2, 3]}]}),
        encoding="utf-8",
    )

    lists = make_lists(tmp_path, code_dir=code_dir, db_dir=db_dir)

    assert lists.list_names() == ["my_list"]
    assert lists.get_elements("my_list") == [1, 2, 3]


def test_add_list_user_true_persists_immediately_to_database_directory(tmp_path):
    code_dir = tmp_path / "code"
    db_dir = tmp_path / "db"
    code_dir.mkdir()
    db_dir.mkdir()
    lists = make_lists(tmp_path, code_dir=code_dir, db_dir=db_dir)

    lists.add_list({"name": "my_list", "type": "string", "elements": ["x", "y"]})

    user_lists_path = db_dir / "model_flow.lists_user.json"
    assert user_lists_path.exists()
    on_disk = json.loads(user_lists_path.read_text(encoding="utf-8"))
    assert on_disk["lists"][0]["name"] == "my_list"
    assert not (db_dir / "model_flow.lists.json").exists()  # shared file untouched


def test_add_list_default_does_not_auto_persist(tmp_path):
    lists = make_lists(tmp_path)

    lists.add_list({"name": "nuts0", "type": "string", "elements": ["AT"]}, user=False)

    assert not (tmp_path / "model_flow.lists.json").exists()

    lists.save()

    assert (tmp_path / "model_flow.lists.json").exists()
    on_disk = json.loads((tmp_path / "model_flow.lists.json").read_text(encoding="utf-8"))
    assert on_disk["lists"][0]["name"] == "nuts0"


def test_add_list_requires_a_name(tmp_path):
    lists = make_lists(tmp_path)

    try:
        lists.add_list({"type": "string", "elements": ["AT"]})
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_get_list_prefers_shared_over_user_on_name_collision(tmp_path):
    lists = make_lists(tmp_path)

    lists.add_list({"name": "nuts0", "elements": ["shared"]}, user=False)
    lists.add_list({"name": "nuts0", "elements": ["user"]}, user=True)

    assert lists.get_list("nuts0") == {"name": "nuts0", "elements": ["shared"]}
    assert lists.list_names() == ["nuts0"]  # deduped, not listed twice


def test_delete_list_user_persists_immediately(tmp_path):
    lists = make_lists(tmp_path)
    lists.add_list({"name": "my_list", "elements": ["x"]})

    assert lists.delete_list("my_list") is True
    assert lists.get_list("my_list") is None

    user_lists_path = tmp_path / "model_flow.lists_user.json"
    on_disk = json.loads(user_lists_path.read_text(encoding="utf-8"))
    assert on_disk["lists"] == []


def test_delete_list_returns_false_when_not_found(tmp_path):
    lists = make_lists(tmp_path)

    assert lists.delete_list("does_not_exist") is False


def test_user_lists_are_loaded_by_a_fresh_lists_instance(tmp_path):
    lists = make_lists(tmp_path)
    lists.add_list({"name": "my_list", "type": "string", "elements": ["x"]})

    reloaded = make_lists(tmp_path)

    assert reloaded.get_list("my_list") == {"name": "my_list", "type": "string", "elements": ["x"]}
