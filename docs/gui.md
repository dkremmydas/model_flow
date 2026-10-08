# GUI and editor support

Model Flow has two GUIs, both thin front ends over the same database and
execution engine as the CLI: a terminal GUI (`run_gui`) and a browser-based
GUI (`run_web_gui`). They share the same task/pipeline definitions and the
same per-task value history (`model_flow.db_user.json`), so values used in
one are offered in the other.

## Terminal GUI

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

## Web GUI

Launch with:

```bash
python model_flow.py run_web_gui --config model_flow.config.json [--host 127.0.0.1] [--port 8765]
```

then open `http://127.0.0.1:8765` in a browser. It binds to this machine
only by default; see [cli-reference.md](cli-reference.md#run_web_gui) before
changing `--host`, since the server has no authentication. The server is
`web_gui/server.py` (Flask + WebSocket); the pages are in `web_gui/static/`.

### Main page

- **Browsing** — a searchable module/task/pipeline tree. Modules whose names
  contain `/` (e.g. `v.main2020/d.policy`) render as a nested, indented
  hierarchy. The config's `Project_title`, if set, is shown in the header.
- **Inspecting and editing parameters** — the same as the terminal GUI:
  editable fields prefilled with defaults, plus a dropdown of previously-used
  values.
- **Running tasks and pipelines** — live-streamed output, with a **Kill**
  button to stop a run. Output streams over a WebSocket that reconnects and
  catches up if the browser drops the connection (for example after sleep),
  so a long run's output isn't lost.
- **Downloading outputs** — after a run, each `role="output_file"` parameter
  of the tasks that ran is listed with a download link, if the file exists.
- **Rebuilding the database** — the **Rebuild database** button re-scans
  `Code_directory`, the same as `build`.
- Panel sizes, collapsed tree branches, and the last selection are
  remembered in the browser.

### Dependency map

The **Dependency map** button opens a graph of how tasks connect through
files. It's built from `model_flow.graph.json` (written by `build`/rebuild):
a task that writes a path as a `role="output_file"` is linked to every task
that reads the same path as a `role="input_file"`. Tasks with no file links
still appear as isolated nodes.

- **Layout** — a layered (dagre) layout, left-to-right or top-to-bottom,
  with adjustable rank and node spacing under **Settings**.
- **Modules** — each module has its own color, shown in a legend. Checkboxes
  show or hide individual modules (**All** / **None** toggle every module),
  and the selection is remembered in the browser.
- **Files** — file links whose path doesn't exist yet are highlighted, so
  you can see which outputs haven't been produced.
- **File inspector** — clicking a connection lists the files it carries in
  the detail panel; clicking an existing file's name expands its structure
  (not its full contents):
  - `.gdx` — its symbols (sets, parameters, variables, equations, aliases),
    via `gamsapi`.
  - `.rds` — the stored object's class; for data frames (including
    data.table, tibble, sf) its rows and columns, for matrices/arrays their
    dimensions and element type, and for lists their elements one level
    deep. This runs `Rscript_exe` from your config.
  - Folders — a listing you can drill into.

  For safety, the inspector only opens files that appear in the dependency
  graph (or files inside a folder that does).

### Current limitation

As with the terminal GUI, the web GUI cannot author pipeline definitions or
loops; loop steps show as a read-only summary.

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
