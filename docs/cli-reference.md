# CLI reference

The main executable is `model_flow.py`:

```bash
python model_flow.py [command] [parameters]*
```

`--config` accepts either a path directly to a config JSON file, or a
directory containing `model_flow.config.json`. Every command below except
`init` requires it.

| Command        | Purpose                                          |
| -------------- | -------------------------------------------------- |
| `init`         | Interactively create the Model Flow config file    |
| `build`        | Discover tasks, pipelines, and lists                |
| `list_tasks`   | List discovered tasks                                |
| `show_task`    | Show one task's metadata                              |
| `run_task`     | Execute one task                                       |
| `run_pipeline` | Execute a declared pipeline                             |
| `run_gui`      | Launch the Textual-based GUI                             |

## init

Interactively creates `model_flow.config.json` and saves it into the chosen
database directory. Use this the first time you set up Model Flow for a
model.

```bash
python model_flow.py init
```

Each answer is validated as it's entered: `Code_directory` and
`Database_directory` must already exist; `Rscript_exe`/`GAMS_exe` must be
existing *files*, not just a containing directory; `Temporary_directory` is
created automatically if missing. An invalid entry re-prompts for that same
field rather than aborting.

## build

Recursively scans `Code_directory`, discovers tasks/pipelines/lists, and
writes `model_flow.db.json`, `model_flow.pipelines.json`, and
`model_flow.lists.json` into `Database_directory`.

```bash
python model_flow.py build --config model_flow.config.json
```

- `--config <file>` (required)

## list_tasks

Lists tasks from the already-built database.

```bash
python model_flow.py list_tasks --config model_flow.config.json [--module <name>]
```

- `--config <file>` (required)
- `--module <name>` (optional) — filter to a single module

## show_task

Displays one task's file path, type, description, and configuration
parameters (name, role, default value).

```bash
python model_flow.py show_task --config model_flow.config.json --module <name> --task <name>
```

- `--config <file>` (required)
- `--module <name>` (required)
- `--task <name>` (required)

`show_task` does **not** take a `--pipeline` flag — pipeline metadata isn't
currently exposed by a dedicated `show_*` command.

## run_task

Executes a single task.

```bash
python model_flow.py run_task --config model_flow.config.json --module <name> --task <name> [options]
```

- `--config <file>` (required)
- `--module <name>` (required)
- `--task <name>` (required)
- `--output_dir <directory>` (optional) — where log/output files are saved;
  defaults to `Temporary_directory` from the config
- `--set PARAM=VALUE` (optional, repeatable) — override a single
  configuration value. **One token** per occurrence, `=`-joined — e.g.
  `--set input_file=data/new_input.csv`, not `--set input_file
  data/new_input.csv`.
- `--parallel` (optional) — run in parallel mode (used together with
  `--range`/`--values`)
- `--range VAR START END STEP` (optional, repeatable) — execute with a
  numeric range of values, e.g. `--range threshold 0.1 1.0 0.2`
- `--values VAR V1 V2 ...` (optional, repeatable) — execute with specific
  values, e.g. `--values method A B C`

Parameter types passed via `--set`/`--range`/`--values` are auto-detected:
numbers (`1`, `3.14`), booleans (`true`, `false`), and strings (quote if the
value contains spaces).

## run_pipeline

Executes every task in a declared pipeline, in order, stopping at the first
failure. Overrides and List-driven loops are declared in
`model_flow.pipelines.json` itself — see [pipelines.md](pipelines.md) — not
via CLI flags.

```bash
python model_flow.py run_pipeline --config model_flow.config.json --module <name> --pipeline <name>
```

- `--config <file>` (required)
- `--module <name>` (required)
- `--pipeline <name>` (required)
- `--output_dir <directory>` (optional) — applied to every task in the
  pipeline; defaults to `Temporary_directory` from the config

Unlike `run_task`, a non-zero pipeline result propagates to the process exit
code.

## run_gui

Launches the Textual-based GUI (see [gui.md](gui.md)).

```bash
python model_flow.py run_gui [--config model_flow.config.json]
```

- `--config <file>` (optional) — defaults to `config.json` if omitted

## Examples

```bash
model_flow build --config "E:/IFM_CAP2/Code/conf/model_flow.config.json"

model_flow list_tasks --module d.estat --config "E:/IFM_CAP2/Code/conf/model_flow.config.json"

model_flow run_task --task 00_initialization --module d.fadn --config "E:/IFM_CAP2/Database2020/model_flow.config.json"

model_flow run_task --task 1_import_agri_csv --module d.fadn \
  --output_dir "E:/IFM_CAP2/Database2020/d.fadn" \
  --config "E:/IFM_CAP2/Code/conf/model_flow.config.json" \
  --set root_csv="E:/IFM_CAP2/original_csv" \
  --set raw_str_map="E:/IFM_CAP2/Model External Data/raw_str_map.2014_and_after.json"

model_flow run_task --config config.json --module v.main2020/d.policy --task 1_create_policy_data \
  --set year=2023 --set input_file=data/new_data.csv

model_flow run_task --config config.json --module model/training --task train_model \
  --parallel --range learning_rate 0.001 0.01 0.002

model_flow run_task --config config.json --module model/training --task train_model \
  --parallel --values optimizer adam sgd --values batch_size 32 64 128

model_flow run_pipeline --config config.json --module v.main2020/d.policy --pipeline run_all
```
