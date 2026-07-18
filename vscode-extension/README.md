# Model Flow Annotations

A VS Code extension that assists authoring `@MODELFLOW_*` annotations in the R / R Markdown / GAMS / Batch scripts that [Model Flow](../README.md) parses into tasks.

## Features (MVP)

- **Commands** (Command Palette, `Ctrl+Shift+P`) that insert a correctly-formed annotation block for the current file's language, with linked tabstops so a config parameter's name always matches its script variable name:
  - `Model Flow: Insert Task Annotation`
  - `Model Flow: Insert Config Annotation`
  - `Model Flow: Insert Description Block`
- **Live diagnostics** flagging, as you type: an unrecognized `@MODELFLOW_*` key, a duplicate `@MODELFLOW_task` in one file, and a `@MODELFLOW_config` whose next line doesn't match the value-line form that filetype requires (mirrors `model_flow build`'s own warnings, but surfaced immediately in the editor).
- **Hover** over an `@MODELFLOW_*` keyword for a short explanation.

## How it stays in sync with the real parser

All of the above is driven by `../annotation-spec.json` (one directory up), the same regex patterns `classes/Task.py` uses to actually parse these files. `test/test_annotation_spec_matches_task_py.py` (in the main Python test suite) fails if that spec and `Task.py`'s patterns ever diverge — so this extension can't silently drift out of sync with what `model_flow build` really accepts.

## Development

```bash
npm install
npm run compile   # copies ../annotation-spec.json in, then runs tsc
```

Then press F5 (or "Run Extension" in the Debug panel) to launch an Extension Development Host with this extension loaded, and open an `.r`/`.rmd`/`.gms`/`.bat` file to try it.

## Not yet implemented

- Attribute-name autocomplete inside a `key="value"` annotation line.
- A live preview panel showing the parsed task name/module/config list for the current file.

See the tracking issue for the full feature list and rationale.
