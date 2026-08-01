# GUI and editor support

## GUI

Launch with:

```bash
python model_flow.py run_gui --config model_flow.config.json
```

The GUI (`textual_gui/app.py`, built on [Textual](https://textual.textualize.io/))
currently supports:

- **Browsing** — a searchable module/task/pipeline tree.
- **Inspecting** — task metadata and configuration parameters, with defaults
  pulled from the database.
- **Editing parameters** — each config row renders as an editable field,
  prefilled with the task's default; a dropdown offers previously-used values
  for that parameter.
- **Running tasks** — executes a task with live-streamed output, and lets you
  terminate a running process.
- **Running pipelines** — browse and run existing pipelines, including
  editing a non-looped task's parameters for one run, and running
  List-driven loop steps (sequential or parallel) end-to-end, with live
  per-step/per-iteration progress.
- **Remembering values** — successfully-used parameter values are saved per
  task (`model_flow.db_user.json`) and offered again next time.
- **Rebuilding the database** — re-scans `Code_directory` and refreshes the
  browse tree without leaving the GUI.

**Current limitation**: the GUI cannot author new pipeline definitions or
define/edit a loop's own declaration — pipelines and loops are still
hand-authored as `model_flow.pipelines.json` (see [pipelines.md](pipelines.md)).
Loop steps render as a read-only summary in the GUI (e.g. "Looped over
nuts_code=nuts2 (parallel, up to 8 workers)").

## VS Code extension

`vscode-extension/` (in this repo) is a separate TypeScript/Node subproject
that assists authoring `@MODELFLOW_*` annotations directly in your editor:

- **Snippets/commands** that insert a correctly-formed `task`/`config`/
  `description_start`–`description_end` block, with linked tabstops so a
  config's name and its script variable name can't drift apart.
- **Live diagnostics** that re-implement the same annotation/value-line
  parsing rules as `classes/Task.py`, flagging a malformed annotation before
  you ever run `build`.
- **Hover help** describing each annotation and attribute.

See `vscode-extension/README.md` in this repository for installation and
development instructions. Not yet implemented: attribute-name completion and
a live single-file parse preview.
