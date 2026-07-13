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
    ])

    with patch("builtins.input", lambda prompt="": next(inputs)):
        config = Config.create_from_user_input()

    assert config.data["Code_directory"] == str(good_code_dir)
    assert config.data["Database_directory"] == str(good_db_dir)
    assert config.data["Rscript_exe"] == str(rscript)
    assert config.data["GAMS_exe"] == str(gams)
    assert tmp_dir.is_dir()  # auto-created for the DIRECTORY_CREATE key

    captured = capsys.readouterr()
    assert "is not a valid directory" in captured.out
    assert "does not point to an existing file" in captured.out
