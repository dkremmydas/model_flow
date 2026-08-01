# Core concepts

A model is organized into **Modules**. Each Module is organized into **Tasks**.
This page is the full glossary; the [README](../README.md#core-concepts) keeps
only brief definitions.

1. **Module** — a collection of tasks with an overarching logic. By
   convention, a module is contained inside a unique folder.

2. **Task** — a unit of work: a single self-contained script. It follows the
   black-box pattern, reading one or more input files and producing one or
   more output files, with its behavior controlled by configuration
   parameters. A task belongs to exactly one module.

3. **Pipeline** — a structured, ordered series of tasks within one module, run
   automatically with no manual intervention, stopping at the first failure.
   A module can have zero or more pipelines; a pipeline belongs to one
   module and cannot span modules.

4. **Workflow** — a structured series of modules, where the output of one
   module feeds another. Workflows belong to the model as a whole rather than
   to any single module. **This is conceptually part of the methodology but
   not yet implemented** in Model Flow — there is no `Workflow` object, file
   format, or CLI/GUI support today.

5. **Task Dependency** — a relationship where one task relies on the
   completion of another before it can begin. Within a pipeline this is
   expressed implicitly by declared task order; there is no separate
   dependency-graph representation.

6. **Job** — a single execution of a task or pipeline (one `run_task` /
   `run_pipeline` invocation, or one GUI-triggered run).

7. **List** — a named, ordered collection of values (e.g. NUTS0/NUTS2 region
   codes) that a pipeline task can loop over. See [lists.md](lists.md).

8. **Annotations** — inline metadata comments (`@MODELFLOW_*`) added to a
   script, giving Model Flow the information it needs (task identity,
   configuration, description) without affecting the script's own execution.
   See [task-annotations.md](task-annotations.md).

## Execution terminology

Model Flow doesn't have a general-purpose "scheduler" — task/pipeline
execution order is either a single `run_task` call or the declared order of a
pipeline's `tasks` list (see [pipelines.md](pipelines.md)). The one component
that does exist is `classes/ExecutionEngine.py`'s `ExecutionEngine`, which
looks up a task or pipeline in the database and runs the underlying script
(`Rscript`, `GAMS`, or `cmd /c` depending on file type), optionally streaming
output and applying parameter overrides. If you're looking for "the scheduler"
or "the execution engine" in the code, this is it — there's no separate
scheduling layer beyond it.
