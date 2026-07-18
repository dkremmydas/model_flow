"""
annotation-spec.json is the single source of truth for @MODELFLOW_* annotation
syntax shared between classes/Task.py (Python) and vscode-extension/
(TypeScript, for live in-editor diagnostics/snippets/hover). This test is the
actual anti-drift mechanism: if classes/Task.py's regex constants change
without annotation-spec.json being updated to match, this fails immediately.
"""

import json
from pathlib import Path

from classes.Task import Task

SPEC_PATH = Path(__file__).resolve().parent.parent / "annotation-spec.json"


def load_spec():
    with open(SPEC_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def test_spec_file_exists():
    assert SPEC_PATH.exists()


def test_attribute_pattern_matches():
    spec = load_spec()
    assert spec["attributePattern"] == Task.ATTRIBUTE_PATTERN


def test_annotation_keys_match():
    spec = load_spec()
    assert set(spec["annotationKeys"]) == {"task", "config", "description_start", "description_end"}


def test_r_and_rmd_patterns_match():
    spec = load_spec()
    assert spec["filetypes"][".r"]["annotationPattern"] == Task.ANNOTATION_PATTERN_R
    assert spec["filetypes"][".r"]["configValuePattern"] == Task.CONFIG_VALUE_PATTERN_R
    assert spec["filetypes"][".rmd"]["annotationPattern"] == Task.ANNOTATION_PATTERN_R
    assert spec["filetypes"][".rmd"]["configValuePattern"] == Task.CONFIG_VALUE_PATTERN_RMD


def test_gams_pattern_matches():
    spec = load_spec()
    assert spec["filetypes"][".gms"]["annotationPattern"] == Task.ANNOTATION_PATTERN_GAMS
    assert spec["filetypes"][".gms"]["configValuePattern"] == Task.CONFIG_VALUE_PATTERN_GAMS
    assert spec["filetypes"][".gms"]["configValuePatternFlags"] == "i"


def test_bat_pattern_matches():
    spec = load_spec()
    assert spec["filetypes"][".bat"]["annotationPattern"] == Task.ANNOTATION_PATTERN_BAT
    assert spec["filetypes"][".bat"]["configValuePattern"] == Task.CONFIG_VALUE_PATTERN_BAT
    assert spec["filetypes"][".bat"]["configValuePatternFlags"] == "i"
