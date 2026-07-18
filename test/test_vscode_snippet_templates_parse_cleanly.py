"""
vscode-extension/src/snippets.ts builds these same templates (VS Code
SnippetString syntax, `${N:default}`) to insert via the extension's commands.
This test guarantees the *filled-in* snippet text -- what a user ends up with
after accepting every tabstop's default -- actually parses cleanly through the
real classes/Task.py parser for every supported filetype, with no warnings and
the expected script_name/script_value captured. If snippets.ts's templates and
Task.py's parsing rules ever drift apart, this is what catches it (the
annotation-spec.json sync test only covers the underlying regexes, not whether
a real snippet's shape satisfies them end-to-end).
"""

import re

from classes.Task import Task

PLACEHOLDER_RE = re.compile(r"\$\{\d+:([^}]*)\}")


def render(template: str) -> str:
    return PLACEHOLDER_RE.sub(r"\1", template)


SNIPPETS = {
    ".r": (
        '#@MODELFLOW_task name="${1:task_name}" module="${2:module_name}"\n\n'
        '#@MODELFLOW_config name="${1:param_name}" role="parameter" type="${2:string}"\n'
        '${1:param_name} = "${3:default_value}",\n'
    ),
    ".rmd": (
        '#@MODELFLOW_task name="${1:task_name}" module="${2:module_name}"\n\n'
        '#@MODELFLOW_config name="${1:param_name}" role="parameter" type="${2:string}"\n'
        '${1:param_name}: "${3:default_value}"\n'
    ),
    ".gms": (
        '*@MODELFLOW_task name="${1:task_name}" module="${2:module_name}"\n\n'
        '*@MODELFLOW_config name="${1:param_name}" role="parameter" type="${2:string}"\n'
        '$ SET ${1:param_name} "${3:default_value}"\n'
    ),
    ".bat": (
        '::@MODELFLOW_task name="${1:task_name}" module="${2:module_name}"\n\n'
        '::@MODELFLOW_config name="${1:param_name}" role="parameter" type="${2:string}"\n'
        'IF NOT DEFINED ${1:param_name} SET "${1:param_name}=${3:default_value}"\n'
    ),
}


def write(tmp_path, ext, text):
    path = tmp_path / f"script{ext}"
    path.write_text(text, encoding="utf-8")
    return path


def test_task_and_config_snippets_parse_cleanly_for_every_filetype(tmp_path, capsys):
    for ext, template in SNIPPETS.items():
        path = write(tmp_path, ext, render(template))
        task = Task(str(path))

        assert task.name == "task_name", ext
        assert task.module == "module_name", ext
        assert task.config == [
            {
                "name": "param_name",
                "role": "parameter",
                "type": "string",
                "script_name": "param_name",
                "script_value": "default_value",
            }
        ], ext

    assert "invalid" not in capsys.readouterr().out.lower()
