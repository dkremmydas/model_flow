# Batch tasks

Windows batch files (`.bat`) use `::` as the annotation comment character:
`::@MODELFLOW_...`. `::` is used rather than `REM` because `cmd.exe` always
treats a `::`-prefixed line as a no-op, whereas `REM` needs a trailing space
to parse as a comment.

## Value line syntax

The **only** valid form for a `@MODELFLOW_config` annotation's value line is
the guarded, quoted assignment, with the guard and `SET` variable names
matching (case-insensitively):

```bat
IF NOT DEFINED VAR SET "VAR=value"
```

An unquoted `set VAR=value`, the unguarded `SET "VAR=value"`, a guard/`SET`
referring to different variable names, or anything else is **not**
recognized — if the line after a `::@MODELFLOW_config` annotation doesn't
match this exact form, `model_flow` prints a warning and skips that parameter
entirely (it won't appear in `model_flow.db.json`; parsing continues with the
rest of the file).

The guard is what makes overrides actually work: the script's own `SET` only
fires when the variable hasn't already been supplied, so a value
`model_flow` injects before launching the script survives rather than being
immediately clobbered by the script's own default.

## Overrides are environment variables, not CLI arguments

Unlike R/GAMS, `.bat` config values are passed to the script as environment
variables rather than command-line arguments — `cmd.exe`'s own argument
parser splits tokens on `=` (not just whitespace), so a `NAME=value` token
can never survive as one positional argument. With the required guarded form
above, `--set`/GUI overrides take effect for `.bat` tasks the same way they
do for R/GAMS/Rmd tasks.

## Example

```bat
::@MODELFLOW_task name="install_deps" module="admin"

::@MODELFLOW_description_start
:: Installs required tools into the target directory.
::@MODELFLOW_description_end

::@MODELFLOW_config name="target_dir" role="parameter" type="string"
IF NOT DEFINED target_dir SET "target_dir=C:\tools"

echo Installing into %target_dir%
```

See [task-annotations.md](task-annotations.md) for the full annotation and
attribute reference.
