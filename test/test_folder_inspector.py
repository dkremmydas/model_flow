import json

import pytest

from classes.Config import Config
from classes.FolderInspector import FolderInspector


def make_config(tmp_path) -> Config:
    config_data = {
        "Code_directory": str(tmp_path),
        "Database_directory": str(tmp_path),
        "Temporary_directory": str(tmp_path),
        "Rscript_exe": "C:/R/Rscript.exe",
        "GAMS_exe": "C:/GAMS/gams.exe",
    }
    return Config(json.dumps(config_data))


def make_folder(tmp_path):
    folder = tmp_path / "outputs"
    folder.mkdir()
    (folder / "b.csv").write_text("a,b\n1,2\n")
    (folder / "a.csv").write_text("x,y\n1,2\n3,4\n")
    (folder / "notes.txt").write_text("hello")
    (folder / "sub").mkdir()
    return folder


def test_inspect_lists_files_and_folders_with_counts_and_sizes(tmp_path):
    config = make_config(tmp_path)
    folder = make_folder(tmp_path)

    result = FolderInspector(config).inspect(folder)

    assert result["format"] == "folder-listing"
    assert result["folder_name"] == "outputs"
    assert result["item_count"] == 4
    assert result["file_count"] == 3
    assert result["dir_count"] == 1
    assert result["total_size_bytes"] == sum(
        (folder / name).stat().st_size for name in ("a.csv", "b.csv", "notes.txt")
    )
    assert result["extension_counts"] == {".csv": 2, ".txt": 1}
    assert result["truncated"] is False


def test_inspect_sorts_dirs_first_then_files_alphabetically(tmp_path):
    config = make_config(tmp_path)
    folder = make_folder(tmp_path)

    result = FolderInspector(config).inspect(folder)

    assert [item["name"] for item in result["items"]] == ["sub", "a.csv", "b.csv", "notes.txt"]
    assert result["items"][0]["type"] == "dir"
    assert result["items"][1]["type"] == "file"


def test_inspect_reports_extension_and_size_per_file(tmp_path):
    config = make_config(tmp_path)
    folder = make_folder(tmp_path)

    result = FolderInspector(config).inspect(folder)

    csv_item = next(item for item in result["items"] if item["name"] == "a.csv")
    assert csv_item["extension"] == ".csv"
    assert csv_item["size_bytes"] == (folder / "a.csv").stat().st_size


def test_inspect_raises_for_non_directory(tmp_path):
    config = make_config(tmp_path)
    file_path = tmp_path / "not_a_folder.txt"
    file_path.write_text("hi")

    with pytest.raises(NotADirectoryError):
        FolderInspector(config).inspect(file_path)


def test_inspect_raises_for_missing_path(tmp_path):
    config = make_config(tmp_path)

    with pytest.raises(NotADirectoryError):
        FolderInspector(config).inspect(tmp_path / "does_not_exist")


def test_inspect_truncates_large_folders(tmp_path, monkeypatch):
    import classes.FolderInspector as folder_inspector_module

    monkeypatch.setattr(folder_inspector_module, "_MAX_ITEMS", 3)
    config = make_config(tmp_path)
    folder = tmp_path / "many"
    folder.mkdir()
    for i in range(10):
        (folder / f"file_{i}.txt").write_text("x")

    result = FolderInspector(config).inspect(folder)

    assert result["file_count"] == 10
    assert result["item_count"] == 10
    assert result["truncated"] is True
    assert len(result["items"]) == 3
