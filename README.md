# Model Flow

**Model Flow** is a tool supporting **Workflow-Oriented Modelling (WORM)** — a methodology for building computational models as modular, explicit, and reproducible data workflows (see [docs/worm-methodology.md](docs/worm-methodology.md)).

Instead of identifying a model solely with its mathematical formulation or its execution script, WORM treats the complete chain of data preparation, parameterization, execution, validation, post-processing, and reporting as the **operational model**. Model execution is one stage among several, not the whole process.

```text
Source data
    ↓
Data preparation
    ↓
Validation
    ↓
Parameter estimation / calibration
    ↓
Model execution
    ↓
Post-processing
    ↓
Evaluation and reporting
```

## The model as a workflow

Scientific and economic models are usually described through their mathematical formulation or their central execution script. In practice, though, it helps to separate three things that are often bundled together under the single word "model":

- **Mathematical model** — the equations, assumptions, constraints, and algorithms.
- **Executable model** — the program that estimates, solves, or simulates the mathematical model (an R script, a GAMS program, a solver run).
- **Operational modelling workflow** — the full process that transforms source data into validated, interpretable results: import, cleaning, validation, parameterization, execution, post-processing, evaluation, reporting.

Model Flow operates primarily at the third level. It does not replace the mathematical or executable model — it organizes the broader workflow in which model execution takes place. The full methodology behind this distinction is in [docs/worm-methodology.md](docs/worm-methodology.md).

## Why Model Flow?

Models that follow the **Workflow-Oriented Modelling** usually consist of many small, independent scripts rather than one program. for example, one script imports raw data, another validates it, another estimates parameters, another runs the solver, others post-process and report on the results. These scripts could often span several languages (R, GAMS, batch files, python) and are chained together by convention — folder structure, filenames, launcher scripts, and the experience of whoever wrote them.

That implicit structure works while the project is small and the original author is around. As the number of scripts grows, the overall logic of the model — which script depends on which, what each one expects as input, what it produces, how to rerun just one step — becomes difficult to see, communicate, or maintain.

Model Flow makes this implicit workflow explicit: it describes scripts as **tasks**, groups them into **modules**, connects them into **pipelines**, and exposes each task's inputs, outputs, and configuration — all discovered from lightweight annotations already present in the scripts, without executing or importing them.

## Principles

- **Explicit transformations** — every meaningful data transformation is represented as a task, not buried inside a larger script.
- **Explicit interfaces** — every task declares its inputs, outputs, and configurable parameters.
- **Independent executability** — a task stays runnable and testable on its own, outside Model Flow.
- **Separation of logic and orchestration** — scripts contain the modelling logic; Model Flow describes and controls how they're organized and run.
- **Language independence** — tasks in different supported languages participate in the same workflow.
- **Artifact-based traceability** — intermediate files are first-class outputs, inspectable and reproducible on their own.
- **Incremental adoption** — existing scripts join the workflow by adding annotation comments, not by being rewritten around a framework.

## Conceptual architecture

```text
Model
│
├── Module: Data preparation
│   └── Pipeline
│       ├── Task: Import data
│       ├── Task: Validate data
│       └── Task: Transform data
│
├── Module: Model execution
│   └── Pipeline
│       ├── Task: Generate parameters
│       ├── Task: Run solver
│       └── Task: Export results
│
└── Module: Reporting
    └── Pipeline
        ├── Task: Aggregate results
        └── Task: Generate report
```

Tasks are the executable units; pipelines order tasks within a module. Model-level composition across modules (a **Workflow**) is part of the methodology's design but **not yet implemented** in the tool — see [Project status](#project-status-and-roadmap).

## Quick start

### 1. Configure Model Flow

```json
{
  "Code_directory": "path/to/model/code",
  "Database_directory": "path/to/model/database",
  "Temporary_directory": "path/to/model/tmp",
  "Rscript_exe": "C:/Program Files/R/R-4.x.x/bin/Rscript.exe",
  "GAMS_exe": "C:/GAMS/gams.exe",
  "Project_title": "My Model"
}
```

Save this as `model_flow.config.json`, or generate it interactively with `python model_flow.py init`. `Project_title` is optional (`init` prompts for it, blank to skip) and is shown in the GUI's title bar when set.

### 2. Annotate a task

```r
#@MODELFLOW_task name="prepare_data" module="data"

#@MODELFLOW_description_start
# Imports and prepares the model input data.
#@MODELFLOW_description_end

#@MODELFLOW_config name="input_file" role="input_file" relative="1"
input_file = "raw/data.csv"

#@MODELFLOW_config name="output_file" role="output_file" relative="1"
output_file = "processed/data.csv"
```

### 3. Discover tasks

```bash
python model_flow.py build --config model_flow.config.json
```

### 4. Inspect available tasks

```bash
python model_flow.py list_tasks --config model_flow.config.json
```

### 5. Run the task

```bash
python model_flow.py run_task --config model_flow.config.json --module data --task prepare_data
```

That's the whole loop: annotate, build, inspect, run. Loops, parallel execution, pipelines, and the GAMS/R Markdown/batch specifics are covered in [Documentation](#documentation).

## Core concepts

- **Task** — the smallest executable unit: one self-contained script (`.r`, `.rmd`, `.gms`, `.bat`) that reads inputs, accepts configuration, and writes outputs.
- **Module** — a collection of related tasks, conventionally one folder. A module name may itself use `/` as a separator (e.g. `"v.main2020/d.policy"`) to express nested modules — a folder containing sub-folders of tasks; the web GUI's task/pipeline tree renders this as an indented hierarchy.
- **Pipeline** — an ordered sequence of tasks within a single module, run automatically, stopping at the first failure.
- **Workflow** — a model-level composition of modules. Conceptually part of WORM; not yet implemented in Model Flow.
- **Job** — one execution instance of a task or pipeline.
- **List** — a named, ordered collection of values (e.g. region codes) that a pipeline task can loop over.

Full definitions, including implementation status for each, are in [docs/concepts.md](docs/concepts.md).

## How Model Flow works

```text
Annotated source scripts
          ↓
    model_flow build
          ↓
model_flow.db.json
model_flow.pipelines.json
model_flow.lists.json
          ↓
       CLI / GUI
          ↓
   Task and pipeline jobs
```

1. Developers annotate existing scripts with `@MODELFLOW_*` comments.
2. `model_flow build` scans the code directory and parses those annotations — without executing any script.
3. It writes machine-readable registries: `model_flow.db.json` (tasks), `model_flow.pipelines.json` (pipelines), `model_flow.lists.json` (lists).
4. The CLI or GUI reads those registries to inspect, configure, and execute tasks and pipelines.

## Task annotations

A task's identity, description, and configuration are declared inline via `{C}@MODELFLOW_{annotation} [{attribute}="{value}"]*` comments, where `{C}` is the language's comment character (`#` in R/Rmd, `*` in GAMS, `::` in `.bat`):

```r
#@MODELFLOW_task name="1_create_baseline_data" module="v.main2020/d.baseline"

#@MODELFLOW_config name="input_file" role="input_file" relative="0"
input_file = "d.fadn/output/data.csv"
```

`@MODELFLOW_config` is always immediately followed by the line that actually assigns the value in the script — that's how a default is captured without running anything. The full attribute reference, the per-language value-line syntax, and how to override a default at run time are in [docs/task-annotations.md](docs/task-annotations.md).

## Pipelines and repeated execution

A pipeline chains tasks within one module and can repeat a task once per element of a List (see [docs/lists.md](docs/lists.md)), sequentially or in parallel:

```json
{
  "module": "v.main2020/d.policy",
  "pipelines": [
    {
      "name": "run_all",
      "tasks": [
        "1_create_policy_data",
        { "task": "2_apply_ecoscheme", "overrides": { "scenario": "baseline" } },
        {
          "task": "3_export_results",
          "loop": { "parameters": { "nuts_code": "nuts2" }, "mode": "parallel", "max_workers": 8 }
        }
      ]
    }
  ]
}
```

Pipelines are declared in a `model_flow.pipelines.json` file inside the module's folder, and run via `run_pipeline` or the GUI. Full validation rules, `zip`/`product` combinations, and output-directory behavior are in [docs/pipelines.md](docs/pipelines.md); lists are documented in [docs/lists.md](docs/lists.md).

## Supported languages

| Language      | File type | Annotation prefix |
| ------------- | --------- | ------------------ |
| R             | `.r`      | `#@MODELFLOW_`     |
| R Markdown    | `.rmd`    | `#@MODELFLOW_`     |
| GAMS          | `.gms`    | `*@MODELFLOW_`     |
| Windows Batch | `.bat`    | `::@MODELFLOW_`    |

Language-specific syntax and worked examples: [docs/r-tasks.md](docs/r-tasks.md), [docs/rmarkdown-tasks.md](docs/rmarkdown-tasks.md), [docs/gams-tasks.md](docs/gams-tasks.md), [docs/batch-tasks.md](docs/batch-tasks.md).

## CLI and GUI

| Command        | Purpose                                        |
| -------------- | ----------------------------------------------- |
| `init`         | Interactively create the Model Flow config file |
| `build`        | Discover tasks, pipelines, and lists            |
| `list_tasks`   | List discovered tasks                           |
| `show_task`    | Show one task's metadata                        |
| `run_task`     | Execute one task                                |
| `run_pipeline` | Execute a declared pipeline                     |
| `run_gui`      | Launch the Textual-based GUI                    |

```bash
python model_flow.py run_task --config model_flow.config.json --module data --task prepare_data --set input_file=raw/other.csv
```

Full flags (including `--range`, `--values`, `--parallel`, `--output_dir`) are in [docs/cli-reference.md](docs/cli-reference.md).

The GUI (`run_gui`) lets you browse modules/tasks/pipelines, edit parameters, run tasks and pipelines, and reuse previously entered values — see [docs/gui.md](docs/gui.md) for its current capabilities and limitations, and for the VS Code extension that assists with authoring annotations.

## Generated files

| File                          | Location            | Managed by | Purpose                          |
| ------------------------------ | -------------------- | ---------- | --------------------------------- |
| `model_flow.config.json`       | User-selected        | User       | Main directories and executables  |
| `model_flow.pipelines.json`    | Inside each module    | User       | That module's pipeline definitions |
| `model_flow.lists.json`        | Anywhere in code tree | User       | Hand-maintained list sources      |
| `model_flow.db.json`           | Database directory    | `build`    | Aggregated task registry          |
| `model_flow.pipelines.json`    | Database directory    | `build`    | Aggregated pipeline registry      |
| `model_flow.lists.json`        | Database directory    | `build`    | Aggregated list registry          |
| `model_flow.db_user.json`      | Database directory    | GUI        | Remembered per-task parameter history |
| `model_flow.lists_user.json`   | Database directory    | User/GUI   | User-defined lists                |
| `model_flow.pipelines_user.json` | Database directory  | User/GUI   | User-authored pipelines           |

Note that `model_flow.pipelines.json` and `model_flow.lists.json` exist as two different things with the same filename: hand-authored sources scattered through `Code_directory`, and the single aggregated copy `build` writes into `Database_directory`.

## Documentation

- [docs/worm-methodology.md](docs/worm-methodology.md) — the WORM methodology, the Model-as-Workflow pattern, and how Model Flow relates to both
- [docs/concepts.md](docs/concepts.md) — full glossary and implementation status
- [docs/task-annotations.md](docs/task-annotations.md) — annotation reference
- [docs/pipelines.md](docs/pipelines.md) — pipeline definition reference
- [docs/lists.md](docs/lists.md) — list definition reference
- [docs/cli-reference.md](docs/cli-reference.md) — full CLI reference
- [docs/gui.md](docs/gui.md) — GUI and VS Code extension
- [docs/r-tasks.md](docs/r-tasks.md) — R task syntax
- [docs/rmarkdown-tasks.md](docs/rmarkdown-tasks.md) — R Markdown task syntax
- [docs/gams-tasks.md](docs/gams-tasks.md) — GAMS task syntax
- [docs/batch-tasks.md](docs/batch-tasks.md) — Batch task syntax

## Project status and roadmap

**Implemented**: task discovery and annotation parsing (R, R Markdown, GAMS, batch); module grouping; pipelines with static overrides and List-driven sequential/parallel loops; CLI (`init`, `build`, `list_tasks`, `show_task`, `run_task`, `run_pipeline`, `run_gui`); GUI browsing, parameter editing, task and pipeline execution, per-task value history; VS Code annotation support.

**Partially implemented**: the GUI can browse and run existing pipelines, including editing a non-looped task's parameters for one run, but cannot yet author new pipeline definitions or loops — those are still hand-authored as `model_flow.pipelines.json`.

**Planned**: Workflows (model-level composition of modules) are part of the Workflow-Oriented Modelling methodology but not yet implemented in Model Flow.

## Contributing

Issues and pull requests are welcome. If you're changing `classes/Task.py`'s annotation regexes, also update `annotation-spec.json` at the repo root — a test asserts the two stay in sync (see [CLAUDE.md](CLAUDE.md) for the full architecture notes this repository is developed against).
