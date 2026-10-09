# Pipelines

A Pipeline is an ordered sequence of steps within a single module, run one
after another via `run_pipeline` (or the GUI). A step is a task, or a
[parallel group](#parallel-groups) of tasks that run at the same time.
Execution stops at the first step that fails — for a looped task, the first
failing iteration; for a parallel group, once its tasks have finished and any
of them failed — and later steps are not run.

## Declaring a pipeline

Pipelines are declared, per module, in a `model_flow.pipelines.json` file
placed inside that module's folder in `Code_directory` (a sibling of the
module's task scripts):

```json
{
  "module": "v.main2020/d.policy",
  "pipelines": [
    {
      "name": "run_all",
      "description": "Runs the full policy pipeline end-to-end.",
      "tasks": [
        "1_create_policy_data",
        {
          "task": "2_apply_ecoscheme",
          "overrides": { "scenario": "baseline" }
        },
        {
          "task": "3_export_results",
          "loop": {
            "parameters": { "nuts_code": "nuts2" },
            "mode": "parallel",
            "max_workers": 8
          }
        }
      ]
    }
  ]
}
```

- `module` (required) — must match a module name that at least one Task in
  `Code_directory` actually declares via its own
  `@MODELFLOW_task module="..."` annotation.
- `pipelines` — a list of `{name, tasks, description?}` objects.
- `tasks` — an ordered list of steps. Each entry is either:
  - a plain **task name** string (matching that task's own `name`, not its
    filename) — runs once, with no overrides; or
  - an object `{task, overrides?, loop?}`:
    - `task` (required) — same task-name rule as the plain-string form.
    - `overrides` (optional) — a static `{script_name: value}` map applied on
      top of the task's own config defaults every run/iteration. Keys must be
      real parameter names (`script_name`) declared in that task's own
      `@MODELFLOW_config` annotations.
    - `loop` (optional) — see below.
  - a **parallel group** `{parallel, max_workers?}` — see
    [Parallel groups](#parallel-groups).

Every referenced `task` must belong to that pipeline's own module — a
pipeline cannot span modules.

`build` (and the GUI's rebuild) normalizes **every** `tasks` entry, however it
was authored, into the `{task, overrides, loop}` object shape before storing
it in the aggregated `model_flow.pipelines.json` — so nothing downstream needs
to branch on which form was used.

## Looping over Lists

`loop` runs a task once per value or combination of values drawn from one or
more named [Lists](lists.md) instead of just once:

- `parameters` (required) — a `{script_name: list_name}` map. Each
  `script_name` must belong to the task's config (and must not also appear in
  `overrides`); each `list_name` must be a List declared somewhere in
  `Code_directory`.
- `combine` — `"zip"` (pairwise; all referenced Lists must have equal length)
  or `"product"` (full cartesian combination). Required only when
  `parameters` has more than one entry; irrelevant (and omittable) for a
  single parameter.
- `mode` — `"sequential"` (default; stops the whole pipeline at the first
  failing iteration) or `"parallel"` (all iterations run to completion
  regardless of any single failure; the step — and pipeline — is judged
  failed afterward if any iteration failed).
- `max_workers` — optional positive integer cap on concurrent iterations for
  `"parallel"` mode; defaults to the config's `Max_workers` (see below), else
  `cpu_count`, always capped at the iteration count, if
  omitted.

## Parallel groups

Steps run one after another. To run several tasks at the same time, wrap them
in a parallel group; the group as a whole is one step:

```json
"tasks": [
  "00_initialization",
  {
    "parallel": [
      "1_import_agri_csv",
      "1_import_prices",
      { "task": "1_import_land", "overrides": { "year": "2023" } }
    ],
    "max_workers": 3
  },
  "2_filtered_load"
]
```

This runs `00_initialization`, then the three imports together, then
`2_filtered_load` once all three have finished.

- `parallel` (required) — a non-empty list of steps, each written exactly like
  an ordinary step (a task name, or `{task, overrides?, loop?}`). Groups can't
  be nested, and a task can appear only once per group.
- `max_workers` (optional) — positive integer cap on how many of the group's
  tasks run at once; defaults to the config's `Max_workers` (see below), else
  the CPU core count, always capped at the number of tasks in the group.

If a task in the group fails, the others still run to completion; the
pipeline then stops (same rule as a parallel loop). A looped task inside a
group runs its own iterations as its `loop` says, so a parallel loop inside a
parallel group uses workers from both limits at once.

Only put tasks in one group if they don't depend on each other's outputs — the
order they start and finish in is not defined.

### Default worker count (`Max_workers` in the config)

`model_flow.config.json` can set an optional `Max_workers`, used by every
parallel loop and parallel group that doesn't declare its own `max_workers`:

- a whole number (e.g. `6`) — that many workers;
- a fraction between 0 and 1 (e.g. `0.5`) — that share of the machine's CPU
  cores, rounded down, at least 1.

Left out, parallel loops and groups use all CPU cores. An invalid value is ignored with a
warning.

A loop step's iterations each run against their own output subdirectory
(`output_dir/<task_name>/<param>=<value>__...`) so repeated runs of the same
task don't collide on output filenames — in particular, `.rmd` tasks generate
an output filename with only minute-granularity, which would otherwise
collide across iterations run within the same clock minute.

## Validation

`build` validates every pipeline it discovers, cross-checked against the
also-discovered Lists. Validation is warn-and-skip at the finest granularity
that makes sense:

- Malformed JSON or a missing `module` skips the whole file.
- A missing/duplicate pipeline `name`, an empty/malformed `tasks` list, or
  *any* problem with a single task entry (unknown task, unknown/overlapping
  override or loop-parameter key, unknown list, mismatched `"zip"` list
  lengths, invalid `combine`/`mode`; for a parallel group, an empty or nested
  group, a task listed twice in it, or an invalid `max_workers`) skips that
  **whole pipeline entry** —
  the same coarse granularity an unknown plain task name always had.
- Duplicate pipeline names for the same module are rejected across the
  *entire* `Code_directory` walk, not just within one file, since multiple
  folders can declare the same module.

## Build aggregation

`model_flow build` discovers every module's `model_flow.pipelines.json`,
validates each pipeline as above, and aggregates the result into
`model_flow.pipelines.json` in `Database_directory` — mirroring how
`model_flow.db.json` aggregates task annotations. Invalid entries are dropped
with a warning rather than failing the whole build.

## Running a pipeline

```bash
python model_flow.py run_pipeline --config model_flow.config.json --module v.main2020/d.policy --pipeline run_all
```

`run_pipeline` takes no `--set`/`--range`/`--values`/`--parallel` flags —
overrides and loops are declared in the pipeline JSON itself. See
[cli-reference.md](cli-reference.md#run_pipeline).

The GUI's pipeline tree lets you browse and run existing pipelines —
including editing a non-looped task's parameters for one run, and List-driven
loop steps end-to-end — but does not yet support authoring new pipeline
definitions or loops from within the GUI itself; those are still hand-authored
as `model_flow.pipelines.json`.
