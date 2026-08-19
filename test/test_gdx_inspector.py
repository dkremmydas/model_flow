import json

import gams.transfer as gt
import gamspy_base
import pytest

from classes.Config import Config
from classes.GdxInspector import GdxInspector


def make_config(tmp_path) -> Config:
    config_data = {
        "Code_directory": str(tmp_path),
        "Database_directory": str(tmp_path),
        "Temporary_directory": str(tmp_path),
        "Rscript_exe": "C:/R/Rscript.exe",
        "GAMS_exe": "C:/GAMS/gams.exe",
    }
    return Config(json.dumps(config_data))


def make_gdx(tmp_path, name="test.gdx"):
    """
    Build a tiny real GDX file at test time via gams.transfer itself (rather
    than mocking or shipping a binary fixture) -- gamsapi[transfer] and
    gamspy_base are ordinary pinned pip packages, not a machine-specific path,
    so exercising the real library in tests is safe and more realistic than
    parsing canned tool output.
    """
    container = gt.Container(system_directory=gamspy_base.directory)
    i = gt.Set(container, "i", records=["a", "b"], description="a test set")
    gt.Parameter(container, "p", domain=[i], records=[("a", 1.0), ("b", 2.0)], description="a test parameter")
    gt.Variable(container, "v", domain=[i], description="a test variable")
    gt.Equation(container, "eq", type="eq", description="a test equation")
    path = tmp_path / name
    container.write(str(path))
    return path


def test_inspect_groups_symbols_by_type_with_dims_domains_and_counts(tmp_path):
    gdx_path = make_gdx(tmp_path)
    inspector = GdxInspector(make_config(tmp_path))

    result = inspector.inspect(gdx_path)

    assert result["format"] == "gdx-symbols"
    assert result["file_name"] == gdx_path.name
    assert result["symbol_count"] == 4
    # Section order: Sets, Parameters, Variables, Equations.
    assert [s["title"] for s in result["sections"]] == ["Sets", "Parameters", "Variables", "Equations"]
    assert result["sections"] == [
        {"title": "Sets", "symbols": [
            {"name": "i", "dimension": 1, "elements": 2, "domains": ["*"], "description": "a test set"},
        ]},
        {"title": "Parameters", "symbols": [
            {"name": "p", "dimension": 1, "elements": 2, "domains": ["i"], "description": "a test parameter"},
        ]},
        {"title": "Variables", "symbols": [
            {"name": "v", "dimension": 1, "elements": 0, "domains": ["i"], "description": "a test variable"},
        ]},
        {"title": "Equations", "symbols": [
            {"name": "eq", "dimension": 0, "elements": 1, "domains": [], "description": "a test equation"},
        ]},
    ]


def test_inspect_omits_description_when_absent(tmp_path):
    container = gt.Container(system_directory=gamspy_base.directory)
    gt.Set(container, "i", records=["a", "b"])
    path = tmp_path / "no_description.gdx"
    container.write(str(path))

    result = GdxInspector(make_config(tmp_path)).inspect(path)

    assert result["sections"] == [
        {"title": "Sets", "symbols": [
            {"name": "i", "dimension": 1, "elements": 2, "domains": ["*"], "description": ""},
        ]},
    ]


def test_inspect_missing_file_raises_file_not_found(tmp_path):
    inspector = GdxInspector(make_config(tmp_path))

    with pytest.raises(FileNotFoundError):
        inspector.inspect(tmp_path / "does_not_exist.gdx")


def test_inspect_invalid_gdx_file_reports_zero_symbols(tmp_path):
    # Verified empirically: gams.transfer.Container.read() fails silently on
    # invalid/non-GDX input (even a truncated real GDX file) rather than
    # raising -- there's no lower-level signal to distinguish that from a
    # genuinely empty GDX file, so this is the real, correct behavior to test
    # rather than an exception.
    bad_path = tmp_path / "not_really_a_gdx.gdx"
    bad_path.write_text("this is not a gdx file", encoding="utf-8")
    inspector = GdxInspector(make_config(tmp_path))

    result = inspector.inspect(bad_path)

    assert result == {
        "format": "gdx-symbols",
        "file_name": bad_path.name,
        "symbol_count": 0,
        "sections": [],
    }
