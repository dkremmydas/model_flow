from unittest.mock import patch

from classes.Config import Config


def test_create_from_user_input_retries_invalid_directory_and_executable_paths(tmp_path, capsys):
    good_code_dir = tmp_path / "code"
    good_code_dir.mkdir()
    good_db_dir = tmp_path / "db"
    good_db_dir.mkdir()
    tmp_dir = tmp_path / "tmp"  # does not exist yet; should be auto-created, not rejected
    rscript = tmp_path / "Rscript.exe"
    rscript.write_text("")
    gams = tmp_path / "gams.exe"
    gams.write_text("")

    inputs = iter([
        str(tmp_path / "nonexistent_code_dir"),  # invalid directory -> should warn and retry
        str(good_code_dir),                      # valid
        str(good_db_dir),
        str(tmp_dir),
        str(tmp_path / "nonexistent.exe"),        # invalid executable -> should warn and retry
        str(rscript),
        str(gams),
        str(tmp_path / "nonexistent_pandoc"),     # invalid optional directory -> should warn and retry
        str(good_code_dir),                       # any existing directory stands in for Pandoc here
        "My Project",                              # optional project title
    ])

    with patch("builtins.input", lambda prompt="": next(inputs)):
        config = Config.create_from_user_input()

    assert config.data["Code_directory"] == good_code_dir.as_posix()
    assert config.data["Database_directory"] == good_db_dir.as_posix()
    assert config.data["Rscript_exe"] == rscript.as_posix()
    assert config.data["GAMS_exe"] == gams.as_posix()
    assert config.data["Pandoc_dir"] == good_code_dir.as_posix()
    assert config.data["Project_title"] == "My Project"
    assert tmp_dir.is_dir()  # auto-created for the DIRECTORY_CREATE key

    captured = capsys.readouterr()
    assert "is not a valid directory" in captured.out
    assert "does not point to an existing file" in captured.out


def test_create_from_user_input_skips_blank_project_title(tmp_path):
    code_dir = tmp_path / "code"
    code_dir.mkdir()
    db_dir = tmp_path / "db"
    db_dir.mkdir()
    tmp_dir = tmp_path / "tmp"
    rscript = tmp_path / "Rscript.exe"
    rscript.write_text("")
    gams = tmp_path / "gams.exe"
    gams.write_text("")

    inputs = iter([
        str(code_dir),
        str(db_dir),
        str(tmp_dir),
        str(rscript),
        str(gams),
        "",  # blank Pandoc_dir -> should be skipped, not stored
        "",  # blank project title -> should be skipped, not stored
    ])

    with patch("builtins.input", lambda prompt="": next(inputs)):
        config = Config.create_from_user_input()

    assert "Pandoc_dir" not in config.data
    assert "Project_title" not in config.data


def test_create_from_user_input_normalizes_backslashes_and_quotes(tmp_path):
    code_dir = tmp_path / "code"
    code_dir.mkdir()
    db_dir = tmp_path / "db"
    db_dir.mkdir()
    rscript = tmp_path / "Rscript.exe"
    rscript.write_text("")
    gams = tmp_path / "gams.exe"
    gams.write_text("")

    inputs = iter([
        str(code_dir).replace("/", "\\"),          # backslash-separated
        f'"{str(db_dir)}"',                          # quoted, as from Explorer's "Copy as path"
        str(tmp_path / "tmp"),
        str(rscript),
        str(gams),
        f'"{str(code_dir)}"',                        # optional Pandoc_dir, quoted too
        "",
    ])

    with patch("builtins.input", lambda prompt="": next(inputs)):
        config = Config.create_from_user_input()

    for key in ("Code_directory", "Database_directory", "Temporary_directory", "Rscript_exe", "GAMS_exe", "Pandoc_dir"):
        assert "\\" not in config.data[key]
        assert '"' not in config.data[key]
    assert config.data["Code_directory"] == code_dir.as_posix()
    assert config.data["Database_directory"] == db_dir.as_posix()
