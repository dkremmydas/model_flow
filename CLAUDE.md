# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Model Flow is a CLI + Textual-based GUI for orchestrating modular simulation models (e.g. IFM-CAP) built from many independent R / R Markdown / GAMS scripts. Scripts declare their identity and configuration via inline `@MODELFLOW_*` annotation comments; `model_flow` scans a code directory, parses those annotations into a JSON "database" (`model_flow.db.json`), and can then run individual tasks (and eventually pipelines) using that metadata.

Terminology (also in README.md): a **Module** is a folder containing **Tasks** (one script each). A **Pipeline** is an ordered sequence of tasks within a module (not yet implemented in code). A **Workflow** is an ordered sequence of modules (not yet implemented).

## Running the tool

Install runtime deps with `pip install -r requirements.txt` (`textual`, `rich`, `numpy`), or `pip install -r requirements-dev.txt` to also get `pytest`.

```
python model_flow.py init                                   # interactively create model_flow.config.json
python model_flow.py build --config=<config.json|dir>        # scan Code_directory, write model_flow.db.json
python model_flow.py list_tasks --config=<config> [--module=<name>]
python model_flow.py show_task --config=<config> --module=<name> --task=<name>
python model_flow.py run_task --config=<config> --module=<name> --task=<name> [--set VAR=VALUE ...] [--parallel] [--range VAR START END STEP] [--values VAR V1 V2 ...] [--output_dir <dir>]
python model_flow.py run_pipeline --config=<config> --module=<name> --pipeline=<name>   # NotImplementedError — stubbed
python model_flow.py run_gui [--config=<config>]              # launches textual_gui/app.py
```

`--config` accepts either a path directly to a config JSON file, or a directory containing `model_flow.config.json`.

Run the test suite with `python -m pytest test/`. Tests live in `test/test_*.py` (pytest auto-discovered). `test/fixtures/` holds pre-existing hand-written fixture files (`test_script.R`, `.rmd`, `.gms`, `.bat`, a sample `ifmcap_flow.config.json`, `module_flow.json`) used for manual exercising rather than by pytest — note those legacy fixtures still use the `@IFMCAP_*` annotation prefix, not the current `@MODELFLOW_*` one, so they won't parse against the current `Task` parser as-is. Coverage is deliberately unit-level: `Task`/`Parser` annotation parsing against in-memory fixture files, and `ExecutionEngine` command construction with `subprocess.call` mocked via `monkeypatch` — there's no end-to-end coverage that actually invokes `Rscript`/`GAMS`, since the configured executable paths are machine-specific and won't exist in most dev/CI environments. When adding coverage for a new code path, follow this same pattern rather than trying to run real scripts.

## Architecture

Data flows: **annotated script → `Task` (parses one file) → `Parser.parse_modules` (walks a directory, builds one `Task` per script) → `model_flow.db.json` (via `build` command) → `Database` (loads/queries that JSON) → `ExecutionEngine` (runs a task's underlying script)**. The CLI (`model_flow.py`) and the GUI (`textual_gui/app.py`) are two front ends over the same `Database`/`ExecutionEngine`/`Config` classes.

- **`classes/Config.py`** — loads/validates `model_flow.config.json` (or an inline JSON string). Required keys: `Code_directory`, `Database_directory`, `Temporary_directory`, `Rscript_exe`, `GAMS_exe`. `Config.get()` is case-insensitive. `is_empty()` signals a failed/invalid load — callers must check it (constructor swallows errors into `self.data = None` rather than raising).

- **`classes/Task.py`** — parses a single script file for `@MODELFLOW_*` annotations. Two parsers: `_parse_file_R` (`.r`/`.rmd`, annotation prefix `#@MODELFLOW_...`) and `_parse_file_GAMS` (`.gms`, annotation prefix `*@MODELFLOW_...`). Recognized annotations: `task` (sets `name`/`module`), `config` (appends an entry to `self.config`, capturing the *next line's* literal assignment as `script_name`/`script_value` — this is how default parameter values are discovered without executing the script), and `description_start`/`description_end` (accumulates free text into `self.description`). A file with no `task` annotation yields `self.name = False` and is skipped by the parser.

- **`classes/Parser.py`** — `Parser.parse_modules(directory)` walks a directory tree (skipping `.git`, `.vscode`, `.svn`, `__pycache__`, `venv`), constructs a `Task` for every `.r`/`.rmd`/`.gms` file, and groups the resulting task dicts by `module` name into `{module_name: [task_dict, ...]}`. This is the dict that gets serialized as `model_flow.db.json` by the `build` CLI command. Also has `parse_range_args`/`parse_value_args`, which turn `--range`/`--values` CLI args into value lists.

- **`classes/Database.py`** — thin JSON-backed store wrapping `model_flow.db.json` (path derived from `Config.Database_directory`). CRUD-ish helpers: `list_modules`, `list_module_tasks`, `get_module`, `get_task`, `add_module`, `add_task`, `delete_task`, `save`. Constructor raises `FileNotFoundError` if the db file hasn't been `build`-generated yet.

- **`classes/ExecutionEngine.py`** — looks up a task via `Database.get_task`, then dispatches on `filetype` to `_execute_r_task`, `_execute_rmd_task`, or `_execute_gams_task`, each of which shells out via `subprocess.call` (R via `Rscript_exe`, `.rmd` via `Rscript_exe -e 'rmarkdown::render(...)'` using `Pandoc_dir`/`GAMS_exe` for env setup, GAMS via `GAMS_exe`). Task `config` entries (`script_name`/`script_value` pairs captured by `Task`) become command-line/params arguments passed to the underlying script — this is the mechanism by which model_flow controls script behavior without editing the scripts themselves. Note the asymmetric path handling: `_execute_r_task` and `_execute_rmd_task` both convert Windows backslashes to forward slashes via a local `r_path()` helper before handing paths to R, but `_execute_gams_task` does not (GAMS accepts native Windows paths) — preserve this distinction if adding a new task-type executor.

- **`model_flow.py`** — argparse-based CLI entry point wiring the above together: `init`, `build`, `list_tasks`, `run_task`, `run_pipeline` (stub), `show_task`, `run_gui`. Known gap: `--set`/`--range`/`--values` are parsed by argparse but not currently threaded through into `ExecutionEngine.execute_task` (parameter overrides at the CLI aren't wired to execution yet).

- **`textual_gui/app.py`** — `ModelFlowApp` (Textual `App`) composes `SelectTask` (a searchable module/task tree, left pane) and `ShowTask` (task detail tree + description log, right pane) side by side. Selecting a task node in `SelectTask` calls `ModelFlowApp.show_task`, which looks up the task via `Database.get_task` and pushes it into `ShowTask.show_task` for rendering as an expandable JSON tree (via `ShowTask.add_json`). `ExecuteTask` widget exists but is currently unwired/incomplete.

## Annotation format (for editing/authoring task scripts)

`{C}@MODELFLOW_{annotation} [{attribute}="{value}"]*` where `{C}` is the language's comment character (`#` in R/Rmd, `*` in GAMS). Full annotation reference and worked GAMS/Rmd examples are in README.md ("Annotations" and "How to prepare files for model_flow" sections) — read those before modifying `Task.py`'s parsing regexes, since the two are tightly coupled (GAMS annotations are matched against `^\*\s*@MODELFLOW_(\w+):?\s*(.*)$`, R/Rmd against `^\s*#@MODELFLOW_(\w+)\s*(.*)$`, and the following line's literal is regex-matched differently per filetype to extract `script_name`/`script_value`).
