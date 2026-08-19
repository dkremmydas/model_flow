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

    assert result.startswith(f"GDX file: {gdx_path.name}\n4 symbols")
    assert "Sets\n  i (1 dim, 2 elements)  domains: *  a test set" in result
    assert "Parameters\n  p (1 dim, 2 elements)  domains: i  a test parameter" in result
    assert "Variables\n  v (1 dim, 0 elements)  domains: i  a test variable" in result
    assert "Equations\n  eq (0 dim, 1 elements)  domains: -  a test equation" in result

    # Section order: Sets, Parameters, Variables, Equations.
    assert result.index("Sets") < result.index("Parameters") < result.index("Variables") < result.index("Equations")


def test_inspect_omits_description_when_absent(tmp_path):
    container = gt.Container(system_directory=gamspy_base.directory)
    gt.Set(container, "i", records=["a", "b"])
    path = tmp_path / "no_description.gdx"
    container.write(str(path))

    result = GdxInspector(make_config(tmp_path)).inspect(path)

    assert "i (1 dim, 2 elements)  domains: *" in result
    # No trailing description text/double-space after the domains segment.
    assert result.rstrip("\n").endswith("domains: *")


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

    assert result == f"GDX file: {bad_path.name}\n0 symbols"
