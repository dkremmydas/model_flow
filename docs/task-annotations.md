# Task annotations

A file becomes a Task once it contains an `@MODELFLOW_task` annotation. Every
annotation has the form:

```text
{C}@MODELFLOW_{annotation} [{attribute name}="{attribute value}"]*
```

`{C}` is the language's comment character: `#` in R/R Markdown, `*` in GAMS,
`::` in `.bat` (chosen because `::` is always a no-op to `cmd.exe`, unlike
`REM`, which needs a trailing space to parse as a comment).

Attributes come in two kinds:

- **Explicit attributes** — written directly on the annotation line by the
  script's author (e.g. `name`, `module`, `role`).
- **Implicit attributes** — parsed automatically from the source code itself
  (e.g. `script_name`, `script_value`, read off the line right after a
  `@MODELFLOW_config` annotation).

## `@MODELFLOW_task`

Declares that the file is a Task.

```r
#@MODELFLOW_task name="1_create_baseline_data" module="v.main2020/d.baseline"
```

- `name` (explicit) — the task's identifier, used in `--task=` and shown in
  the GUI/CLI listings.
- `module` (explicit) — the module the task belongs to. Use a folder-like path
  (`"v.main2020/d.policy"`) to express nested modules.

A file with no `@MODELFLOW_task` annotation is not treated as a task and is
skipped entirely during `build`.

## `@MODELFLOW_description_start` … `@MODELFLOW_description_end`

Free-text documentation for the task. Every line between the two markers that
contains at least one letter is appended to the task's `description`.

```r
#@MODELFLOW_description_start
# Imports and prepares the model input data.
#@MODELFLOW_description_end
```

## `@MODELFLOW_config`

Declares something the user can control: an input file, an output file, or a
plain parameter. The annotation line itself carries the explicit attributes;
the **next line** in the script is not annotation at all — it's read directly
by the parser to capture the script's own hard-coded default.

```r
#@MODELFLOW_config name="input_file" role="input_file" relative="0"
input_file = "d.fadn/output/data.csv"
```

- `name` (explicit) — the logical name of the config entry (what `--set` and
  the GUI refer to).
- `role` (explicit) — one of `input_file`, `output_file`, `parameter`.
- `type` (explicit) — `number` or `string`; only meaningful when
  `role="parameter"`.
- `relative` (explicit) — `1` or `0`, only meaningful for
  `input_file`/`output_file`: whether the path is relative to
  `Database_directory`. Defaults to `1` (relative) if omitted.
- `script_name` (implicit) — the variable name as it appears in the script;
  what actually gets passed back into the script at run time.
- `script_value` (implicit) — the literal default value currently written in
  the script.

Because the value line is read positionally (the line right after the
annotation), a config annotation must sit directly above the assignment it
describes, and the required syntax of that assignment differs per language:

| Filetype | Annotation prefix | Required syntax for the value line |
| --- | --- | --- |
| `.r` | `#@MODELFLOW_...` | `name = value` (optionally trailing comma), e.g. `input_file = "data.csv",` |
| `.rmd` | `#@MODELFLOW_...` (inside the `params:` YAML block) | `name: value`, e.g. `input_file: "data.csv"` |
| `.gms` | `*@MODELFLOW_...` | `$ SET NAME "value"` |
| `.bat` | `::@MODELFLOW_...` | `IF NOT DEFINED NAME SET "NAME=value"` — guarded, quoted form only; see [batch-tasks.md](batch-tasks.md) |

If the line after a `.bat` `@MODELFLOW_config` annotation isn't exactly
`IF NOT DEFINED VAR SET "VAR=value"` (a bare `set VAR=value`, the old
unguarded `SET "VAR=value"`, a guard/`SET` referring to different variable
names, etc. all fail to match), the parser prints a warning and drops that
config entry entirely rather than recording something malformed — this is a
deliberate, narrow contract, not a bug.

## Overriding defaults at run time

The `script_value` captured from the script is only the *default*. It can be
overridden per-run without touching the script:

- CLI: `--set PARAM=VALUE` (repeatable) on `run_task` — see
  [cli-reference.md](cli-reference.md).
- GUI: editing a config row's input field before running; previously-used
  values are remembered per task (`model_flow.db_user.json`) and offered
  again via a dropdown.

Either mechanism produces the same `{script_name: value}` override map,
applied to a deep copy of the task so the underlying database is never
mutated.

## Editor support

`vscode-extension/` (in this repo) is a VS Code extension that assists
authoring the annotations above directly in your script files — see
[gui.md](gui.md#vs-code-extension).
