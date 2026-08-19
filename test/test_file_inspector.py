import json

import pytest

from classes.Config import Config
from classes.FileInspector import FileInspector
from classes.GdxInspector import GdxInspector
from classes.RdsInspector import RdsInspector


def make_config(tmp_path) -> Config:
    config_data = {
        "Code_directory": str(tmp_path),
        "Database_directory": str(tmp_path),
        "Temporary_directory": str(tmp_path),
        "Rscript_exe": "C:/R/Rscript.exe",
        "GAMS_exe": "C:/GAMS/gams.exe",
    }
    return Config(json.dumps(config_data))


def test_get_inspector_resolves_known_extension(tmp_path):
    config = make_config(tmp_path)

    inspector = FileInspector.get_inspector("model.gdx", config)

    assert isinstance(inspector, GdxInspector)


def test_get_inspector_is_case_insensitive(tmp_path):
    config = make_config(tmp_path)

    inspector = FileInspector.get_inspector("MODEL.GDX", config)

    assert isinstance(inspector, GdxInspector)


def test_get_inspector_resolves_rds_extension(tmp_path):
    config = make_config(tmp_path)

    inspector = FileInspector.get_inspector("model.rds", config)

    assert isinstance(inspector, RdsInspector)


def test_get_inspector_returns_none_for_unknown_extension(tmp_path):
    config = make_config(tmp_path)

    assert FileInspector.get_inspector("data.csv", config) is None


def test_inspect_path_returns_friendly_message_for_unsupported_type(tmp_path):
    config = make_config(tmp_path)

    result = FileInspector.inspect_path("data.csv", config)

    assert result == {"format": "unsupported", "message": "No inspector available for '.csv' files yet."}


def test_inspect_path_reports_missing_extension(tmp_path):
    config = make_config(tmp_path)

    result = FileInspector.inspect_path("Makefile", config)

    assert result == {"format": "unsupported", "message": "No inspector available for '(no extension)' files yet."}


def test_base_inspect_raises_not_implemented(tmp_path):
    config = make_config(tmp_path)

    with pytest.raises(NotImplementedError):
        FileInspector(config).inspect("whatever")
