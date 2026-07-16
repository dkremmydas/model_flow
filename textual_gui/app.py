import asyncio
import re

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Static, Tree, Log, Select, Footer, Header, Input
from textual.widget import Widget
from textual.widgets.tree import TreeNode

from rich.text import Text

from classes.Config import Config
from classes.Database import Database
from classes.ExecutionEngine import ExecutionEngine, ExecutionResult
from classes.Lists import Lists
from classes.Parser import Parser
from classes.Task import Task



class SelectTask(Widget):

    tree = None  # Reactive attribute to hold the tree widget
    selected_node = None

    DEFAULT_CSS = """
    SelectTask {
        layout: vertical;
        width: 50%;
    }
    #search-container {
        height: 4;
        padding: 0;
        margin: 1;
        width: 100%;
    }
    #module-search {
        padding: 0;
        margin: 0;
        height: auto;
        width: 100%;
    }


    """


    def __init__(self,  modelflowapp: "ModelFlowApp"):
        super().__init__(id= "select-task")
        self.modelflowapp = modelflowapp
        self.database = modelflowapp.database
        self.modules = self.database.list_modules() or ["No modules available"]  # Load the list of modules or provide a fallback
        self.module_tasks = {module: self.database.list_module_tasks(module) for module in self.modules}
        self.module_pipelines = {module: self.database.list_pipelines(module) for module in self.modules}
        self.tree = Tree("Modules", id="tree-view")


    def compose(self) -> ComposeResult:
        """Compose the layout of the application."""
        yield Vertical(
                    Static("Search for Tasks or Modules:"),
                    Input(placeholder="Start typing...", id="module-search"),
                    id="search-container",
                )
        # Tree view for modules and tasks
        yield self.tree


    def on_mount(self) -> None:
        """Initialize the application when it starts."""
        self.filter_tree("")

    def refresh_from_database(self) -> None:
        """Reload modules/tasks from the database (e.g. after a rebuild) and re-render the tree."""
        self.modules = self.database.list_modules() or ["No modules available"]
        self.module_tasks = {module: self.database.list_module_tasks(module) for module in self.modules}
        self.module_pipelines = {module: self.database.list_pipelines(module) for module in self.modules}
        search_input = self.query_one("#module-search", Input)
        self.filter_tree(search_input.value)

    def on_input_changed(self, event: Input.Changed) -> None:
        """Filter the module/task tree as the user types."""
        if event.input.id != "module-search":
            return
        self.filter_tree(event.value)

    def filter_tree(self, query: str) -> None:
        """Rebuild the tree, showing only modules/tasks matching `query` (case-insensitive)."""
        query = query.strip().lower()
        self.tree.clear()
        root = self.tree.root

        for module, tasks in self.module_tasks.items():
            pipelines = self.module_pipelines.get(module, [])
            module_matches = query in module.lower()
            matching_tasks = tasks if module_matches else [t for t in tasks if query in t.lower()]
            matching_pipelines = pipelines if module_matches else [p for p in pipelines if query in p.lower()]
            if module_matches or matching_tasks or matching_pipelines:
                module_node = root.add(module)
                tasks_node = module_node.add("Tasks")
                for task in matching_tasks:
                    tasks_node.add(task)
                pipelines_node = module_node.add("Pipelines")
                for pipeline in matching_pipelines:
                    pipelines_node.add(pipeline)
        root.expand()

    async def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        """Handle tree node selection."""
        self.selected_node = event.node
        await self.modelflowapp.select_task(self.selected_node)




class ShowTask(Widget):

    DEFAULT_CSS = """
    ShowTask {
        layout: vertical;
        width: 49%;
        border: solid red;
        margin: 1;
        padding: 1;
    }

    #description {
        height: 30%;
        width: 100%;
    }

    #config-editor {
        height: 1fr;
        width: 100%;
    }

    .param-row {
        height: auto;
        width: 100%;
    }

    .param-label {
        width: 30%;
        padding-top: 1;
    }

    .param-input {
        width: 40%;
    }

    .param-select {
        width: 30%;
    }

    .pipeline-task-header {
        text-style: bold;
        padding-top: 1;
    }
    """

    def __init__(self, modelflowapp: "ModelFlowApp") -> None:
        """Initialize the widget."""
        super().__init__(id="show-task")
        self.modelflowapp = modelflowapp
        # Named task_tree/description_log (not tree/log) to avoid colliding with
        # Widget's own built-in `tree`/`log` devtools properties (no setter).
        self.task_tree = Tree("Select a Task or a Pipeline", id="task-log")
        self.description_log = Log(id="description")
        self.description_log.auto_scroll = False
        self.config_editor = VerticalScroll(id="config-editor")
        self.current_task = None
        # Set only while a pipeline (not a single task) is being shown: (module, pipeline_name).
        self.current_pipeline = None
        # widget_id (sans "input-" prefix) -> (task_name, script_name, default_value),
        # populated by show_pipeline so on_input_submitted knows what/where to persist.
        self.pipeline_param_defaults = {}

    def compose(self) -> ComposeResult:
        """Compose the layout of the application."""
        with Vertical():
            yield self.task_tree
            yield self.description_log
            yield self.config_editor

    @staticmethod
    def _param_widget_id(script_name: str) -> str:
        """Sanitize a script_name into a valid Textual widget id fragment."""
        return re.sub(r"[^a-zA-Z0-9_-]", "_", script_name)

    @classmethod
    def _pipeline_widget_id(cls, task_name: str, script_name: str) -> str:
        """Sanitize a (task_name, script_name) pair into a unique widget id fragment --
        a pipeline can list several tasks that each declare the same script_name, so
        show_task's own bare `_param_widget_id(script_name)` isn't unique enough here."""
        return "pipeline-" + cls._param_widget_id(f"{task_name}_{script_name}")

    async def show_task(self, task: dict) -> None:
        """Update the task in the ShowTask widget."""
        self.current_task = task
        self.current_pipeline = None
        self.pipeline_param_defaults = {}

        # Show the read-only task metadata (everything but config/description/module/name,
        # which are either shown elsewhere or duplicated in the root label below).
        self.task_tree.clear()
        task_meta = {k: v for k, v in task.items() if k not in ("config", "description", "module", "name")}
        self.add_json(Text(f"{task.get('module', '')}/{task.get('name', '')}"), self.task_tree.root, task_meta)

        # Show the description
        self.description_log.clear()
        self.description_log.write_line(task.get("description", ""))
        self.description_log.scroll_home(animate=False)

        # Show editable config parameters, with a history picker per parameter
        await self.config_editor.remove_children()
        module = task.get("module")
        task_name = task.get("name")
        database = self.modelflowapp.database
        history = database.get_user_values(module, task_name) if database else {}

        rows = []
        for param in task.get("config", []):
            script_name = param.get("script_name")
            if not script_name:
                continue
            widget_id = self._param_widget_id(script_name)
            row_children = [
                Static(f"{script_name} ({param.get('role', 'parameter')})", classes="param-label"),
                Input(value=str(param.get("script_value", "")), id=f"input-{widget_id}", classes="param-input"),
            ]
            values = history.get(script_name, [])
            if values:
                row_children.append(
                    Select(
                        [(value, value) for value in reversed(values)],
                        id=f"select-{widget_id}",
                        classes="param-select",
                        allow_blank=True,
                        prompt="History",
                    )
                )
            rows.append(Horizontal(*row_children, classes="param-row"))

        if rows:
            await self.config_editor.mount(*rows)

    async def show_pipeline(self, module: str, pipeline: dict) -> None:
        """Update the right panel with a pipeline's ordered task list, and an editable
        config form per task (mirrors show_task's per-parameter rows). There's no
        separate "run" step for a pipeline yet to persist history after (unlike
        show_task, whose overrides are recorded only once execution completes), so
        edits are persisted to model_flow.db_user.json as soon as they're submitted
        (see on_input_submitted)."""
        self.current_task = None
        self.current_pipeline = (module, pipeline.get("name"))
        self.pipeline_param_defaults = {}

        self.task_tree.clear()
        pipeline_meta = {k: v for k, v in pipeline.items() if k not in ("description", "name")}
        self.add_json(Text(f"{module}/{pipeline.get('name', '')} (pipeline)"), self.task_tree.root, pipeline_meta)
        self.task_tree.root.expand()

        self.description_log.clear()
        self.description_log.write_line(pipeline.get("description", ""))
        self.description_log.scroll_home(animate=False)

        await self.config_editor.remove_children()
        database = self.modelflowapp.database

        sections = []
        for task_name in pipeline.get("tasks", []):
            task = database.get_task(module, task_name) if database else None
            if not task:
                continue

            sections.append(Static(task_name, classes="pipeline-task-header"))
            history = database.get_user_values(module, task_name) if database else {}

            for param in task.get("config", []):
                script_name = param.get("script_name")
                if not script_name:
                    continue
                default_value = str(param.get("script_value", ""))
                widget_id = self._pipeline_widget_id(task_name, script_name)
                self.pipeline_param_defaults[widget_id] = (task_name, script_name, default_value)

                row_children = [
                    Static(f"{script_name} ({param.get('role', 'parameter')})", classes="param-label"),
                    Input(value=default_value, id=f"input-{widget_id}", classes="param-input"),
                ]
                values = history.get(script_name, [])
                if values:
                    row_children.append(
                        Select(
                            [(value, value) for value in reversed(values)],
                            id=f"select-{widget_id}",
                            classes="param-select",
                            allow_blank=True,
                            prompt="History",
                        )
                    )
                sections.append(Horizontal(*row_children, classes="param-row"))

        if sections:
            await self.config_editor.mount(*sections)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Persist a pipeline task's edited parameter to model_flow.db_user.json once
        the user commits it (Enter) -- there's no separate "run" step for pipelines
        to persist after, and persisting on every keystroke (Input.Changed) would
        flood the history with partial edits."""
        widget_id = event.input.id or ""
        if not widget_id.startswith("input-pipeline-") or not self.current_pipeline:
            return
        meta = self.pipeline_param_defaults.get(widget_id[len("input-"):])
        database = self.modelflowapp.database
        if not meta or not database:
            return
        task_name, script_name, default_value = meta
        if event.value == default_value:
            return
        module, _ = self.current_pipeline
        database.add_user_value(module, task_name, script_name, event.value)

    def on_select_changed(self, event: Select.Changed) -> None:
        """Fill a parameter's Input with the value picked from its history Select."""
        select_id = event.select.id or ""
        if not select_id.startswith("select-") or event.value is Select.BLANK:
            return
        widget_id = select_id[len("select-"):]
        input_widget = self.query_one(f"#input-{widget_id}", Input)
        input_widget.value = str(event.value)

    def get_overrides(self) -> dict:
        """Return {script_name: value} for parameters whose Input differs from the task default."""
        overrides = {}
        if not self.current_task:
            return overrides
        for param in self.current_task.get("config", []):
            script_name = param.get("script_name")
            if not script_name:
                continue
            widget_id = self._param_widget_id(script_name)
            try:
                input_widget = self.query_one(f"#input-{widget_id}", Input)
            except Exception:
                continue
            value = input_widget.value
            if value != str(param.get("script_value", "")):
                overrides[script_name] = value
        return overrides

    def get_pipeline_overrides(self) -> dict:
        """Return {task_name: {script_name: value}} for pipeline-task parameters whose
        Input differs from that task's default. Mirrors get_overrides, but keyed per
        task since show_pipeline renders one editable form per task in the pipeline."""
        overrides: dict = {}
        if not self.current_pipeline:
            return overrides
        for widget_id, (task_name, script_name, default_value) in self.pipeline_param_defaults.items():
            try:
                input_widget = self.query_one(f"#input-{widget_id}", Input)
            except Exception:
                continue
            value = input_widget.value
            if value != default_value:
                overrides.setdefault(task_name, {})[script_name] = value
        return overrides

    @classmethod
    def add_json(cls, root_name, node: TreeNode, json_data: object) -> None:
        """Adds JSON data to a node.

        Args:
            node (TreeNode): A Tree node.
            json_data (object): An object decoded from JSON.
        """

        from rich.highlighter import ReprHighlighter

        highlighter = ReprHighlighter()

        def add_node(name: str, node: TreeNode, data: object) -> None:
            """Adds a node to the tree.

            Args:
                name (str): Name of the node.
                node (TreeNode): Parent node.
                data (object): Data associated with the node.
            """
            if isinstance(data, dict):
                node.set_label(Text(f"{{}} {name}"))
                for key, value in data.items():
                    new_node = node.add("")
                    add_node(key, new_node, value)
            elif isinstance(data, list):
                node.set_label(Text(f"[] {name}"))
                for index, value in enumerate(data):
                    new_node = node.add("")
                    add_node(str(index), new_node, value)
            else:
                node.allow_expand = False
                if name:
                    label = Text.assemble(
                        Text.from_markup(f"[b]{name}[/b]="), highlighter(repr(data))
                    )
                else:
                    label = Text(repr(data))
                node.set_label(label)

        add_node(root_name, node, json_data)




class ExecuteTask(Widget):

    DEFAULT_CSS = """
    ExecuteTask {
        layout: vertical;
        width: 100%;
        height: 1fr;
        border: solid green;
        margin: 1;
        padding: 1;
    }

    #execute-status {
        height: auto;
    }

    #execute-output {
        height: 1fr;
    }
    """

    def __init__(self) -> None:
        """Initialize the widget."""
        super().__init__(id="execute-task")
        self.status = Static("Select a task, then press ctrl+r to execute it.", id="execute-status")
        self.output_log = Log(id="execute-output")

    def compose(self) -> ComposeResult:
        """Compose the layout of the application."""
        with Vertical():
            yield self.status
            yield self.output_log

    def set_status(self, message: str) -> None:
        self.status.update(message)

    def start_running(self, message: str) -> None:
        """Announce a run has begun: show the status message, a persistent header
        sub-title so it's visible even while this panel is toggled off (ctrl+o) in
        favor of the browse view, and a clean output log ready to receive streamed
        output."""
        self.set_status(message)
        if self.app:
            self.app.sub_title = message
        self.output_log.clear()

    def announce_step(self, message: str) -> None:
        """Update status/sub-title mid-run without clearing the output log -- used
        between steps of a multi-task pipeline run, where each task's output should
        accumulate in the same log rather than being wiped like start_running does
        for a single task run."""
        self.set_status(message)
        if self.app:
            self.app.sub_title = message

    def append_output(self, line: str) -> None:
        """Append one line of live-streamed subprocess output. Must only be called
        from the UI thread -- callers driving execution from a worker thread
        should marshal through e.g. Textual's App.call_from_thread."""
        self.output_log.write_line(line)

    def finish_running(self) -> None:
        """Clear the header sub-title once a run has ended. Every code path that
        ends a run must call this (directly or via show_result/show_error)."""
        if self.app:
            self.app.sub_title = ""

    def show_result(self, module: str, task_name: str, result, streamed: bool = False) -> None:
        """Report a finished run's result. `streamed=True` means output was already
        appended live via append_output as it happened, so it isn't rewritten here
        (which would otherwise duplicate it) -- only the final status line updates."""
        self.finish_running()
        if not streamed:
            self.output_log.clear()
            if isinstance(result, ExecutionResult):
                if result.stdout:
                    self.output_log.write(result.stdout)
                if result.stderr:
                    self.output_log.write(result.stderr)
        returncode = result.returncode if isinstance(result, ExecutionResult) else result
        status = "succeeded" if returncode == 0 else f"failed (exit code {returncode})"
        self.output_log.write_line(f"Task {module}/{task_name}, finished")
        self.set_status(f"{module}/{task_name} {status}")

    def show_error(self, module: str, task_name: str, error: str) -> None:
        self.finish_running()
        self.output_log.clear()
        self.output_log.write(error)
        self.set_status(f"{module}/{task_name} failed to start: {error}")

    def show_aborted(self, module: str, task_name: str) -> None:
        """Report a run that was stopped via action_kill_task (ctrl+k), rather than
        one that ran to completion (show_result) or never started (show_error)."""
        self.finish_running()
        self.output_log.write_line(f"Task {module}/{task_name}, aborted")
        self.set_status(f"{module}/{task_name} aborted")




class ModelFlowApp(App):
    """A Textual-based GUI for the Model Flow application."""

    DEFAULT_CSS = """
        Screen {
            background: black;
            color: white;
            layout: vertical;
        }
        #startup-error {
            margin: 2;
            padding: 2;
            border: solid red;
        }
    """


    BINDINGS = [
        ("escape", "quit", "Quit"),
        ("ctrl+r", "execute_task", "Execute Task/Pipeline"),
        ("ctrl+k", "kill_task", "Abort"),
        ("ctrl+o", "toggle_output", "Toggle Output"),
        ("ctrl+b", "rebuild_database", "Rebuild DB"),
    ]



    def __init__(self, config: Config = None) -> None:
        """Initialize the application."""
        super().__init__()
        self.config = config  # Store the configuration if needed
        self.database = None
        self.engine = None
        self.lists = None
        self.execute_panel = None
        self.main_view = None
        self.selected_task = None  # (module, task_name) of the currently selected task
        self.selected_pipeline = None  # (module, pipeline_name) of the currently selected pipeline
        self.startup_error = None
        self.current_process = None  # subprocess.Popen of the task currently running, if any
        self.execution_cancelled = False  # set just before terminating current_process

        try:
            self.database = Database(self.config)
            self.engine = ExecutionEngine(self.config)
            self.lists = Lists(self.config)
        except FileNotFoundError as e:
            self.startup_error = str(e)

        database_directory = self.config.get("Database_directory", "Not specified") if self.config else "Not specified"
        self.title = f"Model Flow - Database Directory: {database_directory}"


    def compose(self) -> ComposeResult:
        """Compose the layout of the application."""

        yield Header()

        if self.startup_error:
            yield Vertical(
                Static(
                    "No task database found.\n\n"
                    f"{self.startup_error}\n\n"
                    "Run `python model_flow.py build --config=<config>` first, then relaunch the GUI.",
                    id="startup-error",
                ),
                id="container",
            )
        else:
            self.execute_panel = ExecuteTask()
            self.execute_panel.display = False
            self.main_view = Horizontal(
                SelectTask(self),
                ShowTask(self),
                id="container"
            )
            yield self.main_view
            yield self.execute_panel

        yield Footer()

    async def select_task(self, node) -> None:
        """Update the right panel (ShowTask) for the selected tree node.

        Tree shape is root("Modules") -> module -> "Tasks"/"Pipelines" -> leaf.
        Selecting a module node or a "Tasks"/"Pipelines" group node itself is a
        no-op; a leaf under "Tasks" shows the editable task view (and arms ctrl+r
        to run that one task), a leaf under "Pipelines" shows the pipeline's
        editable per-task forms (and arms ctrl+r to run the whole pipeline).
        """
        parent = node.parent
        if parent is None or parent.parent is None:
            return

        group_label = str(parent.label)
        module_name = str(parent.parent.label)
        show_task_widget = self.query_one("#show-task", ShowTask)

        if group_label == "Tasks":
            task_name = str(node.label)
            task = self.database.get_task(module_name, task_name)
            if not task:
                return
            self.selected_task = (module_name, task_name)
            self.selected_pipeline = None
            await show_task_widget.show_task(task)
        elif group_label == "Pipelines":
            pipeline_name = str(node.label)
            pipeline = self.database.get_pipeline(module_name, pipeline_name)
            if not pipeline:
                return
            self.selected_task = None
            self.selected_pipeline = (module_name, pipeline_name)
            await show_task_widget.show_pipeline(module_name, pipeline)

    def action_toggle_output(self) -> None:
        """Toggle the execution output panel between full-screen and hidden.

        The two are mutually exclusive: showing output hides the browse view
        (SelectTask/ShowTask) so the output panel fills the screen, and hiding
        it restores the browse view.
        """
        if not self.execute_panel or not self.main_view:
            return
        show_output = not self.execute_panel.display
        self.execute_panel.display = show_output
        self.main_view.display = not show_output

    async def action_execute_task(self) -> None:
        """Execute the currently selected task or pipeline (ctrl+r)."""
        if self.selected_task:
            await self._execute_selected_task()
        elif self.selected_pipeline:
            await self._execute_selected_pipeline()

    async def _execute_selected_task(self) -> None:
        """Execute the currently selected task with any user-edited parameter overrides."""
        if not self.database or not self.engine or not self.selected_task or not self.execute_panel:
            return
        if self.current_process is not None and self.current_process.poll() is None:
            return  # a task is already running -- ctrl+k aborts it first

        module, task_name = self.selected_task
        show_task_widget = self.query_one("#show-task", ShowTask)
        overrides = show_task_widget.get_overrides()

        # Surface the panel full-screen automatically so a run's result is never missed.
        self.execute_panel.display = True
        if self.main_view:
            self.main_view.display = False
        self.execution_cancelled = False
        self.execute_panel.start_running(f"Running {module}/{task_name}... (ctrl+k to abort)")

        # execute_task runs on a worker thread; append_output must only touch
        # widgets from the UI thread, so marshal each line back via call_from_thread.
        def on_output(line: str) -> None:
            self.call_from_thread(self.execute_panel.append_output, line)

        # Give action_kill_task something to terminate() -- safe to call from another
        # thread than the one reading the process's output.
        def on_process_start(process) -> None:
            self.current_process = process

        try:
            result = await asyncio.to_thread(
                self.engine.execute_task,
                module,
                task_name,
                None,
                overrides,
                True,
                on_output,
                on_process_start,
            )
        except Exception as e:
            self.current_process = None
            if self.execution_cancelled:
                self.execute_panel.show_aborted(module, task_name)
            else:
                self.execute_panel.show_error(module, task_name, str(e))
            return

        self.current_process = None
        if self.execution_cancelled:
            self.execute_panel.show_aborted(module, task_name)
        else:
            self.execute_panel.show_result(module, task_name, result, streamed=True)

        for script_name, value in overrides.items():
            self.database.add_user_value(module, task_name, script_name, value)

    async def _execute_selected_pipeline(self) -> None:
        """Execute every task in the currently selected pipeline, sequentially, in
        declared order, stopping at the first task that fails -- mirrors the CLI's
        run_pipeline semantics (model_flow.py's run_pipeline). Unlike a single-task
        run, the output log is cleared once at the start and then accumulates every
        task's streamed output in turn (announce_step updates the status/sub-title
        between tasks without wiping that log)."""
        if not self.database or not self.engine or not self.selected_pipeline or not self.execute_panel:
            return
        if self.current_process is not None and self.current_process.poll() is None:
            return  # a task is already running -- ctrl+k aborts it first

        module, pipeline_name = self.selected_pipeline
        pipeline = self.database.get_pipeline(module, pipeline_name)
        if not pipeline:
            return
        task_names = pipeline.get("tasks", [])

        show_task_widget = self.query_one("#show-task", ShowTask)
        pipeline_overrides = show_task_widget.get_pipeline_overrides()

        self.execute_panel.display = True
        if self.main_view:
            self.main_view.display = False
        self.execution_cancelled = False
        self.execute_panel.output_log.clear()
        self.execute_panel.announce_step(f"Running pipeline {module}/{pipeline_name}... (ctrl+k to abort)")

        # Give action_kill_task something to terminate() -- safe to call from another
        # thread than the one reading the process's output.
        def on_process_start(process) -> None:
            self.current_process = process

        for index, task_name in enumerate(task_names, start=1):
            overrides = pipeline_overrides.get(task_name, {})
            step = f"[{index}/{len(task_names)}]"
            self.execute_panel.announce_step(
                f"Running pipeline {module}/{pipeline_name} {step}: {task_name}... (ctrl+k to abort)"
            )
            self.execute_panel.output_log.write_line(f"=== {step} {task_name} ===")

            def on_output(line: str) -> None:
                self.call_from_thread(self.execute_panel.append_output, line)

            try:
                result = await asyncio.to_thread(
                    self.engine.execute_task,
                    module,
                    task_name,
                    None,
                    overrides,
                    True,
                    on_output,
                    on_process_start,
                )
            except Exception as e:
                self.current_process = None
                self.execute_panel.finish_running()
                if self.execution_cancelled:
                    self.execute_panel.output_log.write_line(f"Pipeline {module}/{pipeline_name}, aborted at {task_name}")
                    self.execute_panel.set_status(f"Pipeline {module}/{pipeline_name} aborted")
                else:
                    self.execute_panel.output_log.write_line(f"Task {task_name} failed to start: {e}")
                    self.execute_panel.set_status(f"Pipeline {module}/{pipeline_name} failed to start task {task_name}: {e}")
                return

            self.current_process = None

            for script_name, value in overrides.items():
                self.database.add_user_value(module, task_name, script_name, value)

            if self.execution_cancelled:
                self.execute_panel.finish_running()
                self.execute_panel.output_log.write_line(f"Pipeline {module}/{pipeline_name}, aborted at {task_name}")
                self.execute_panel.set_status(f"Pipeline {module}/{pipeline_name} aborted")
                return

            returncode = result.returncode
            self.execute_panel.output_log.write_line(f"Task {module}/{task_name}, finished (exit {returncode})")

            if returncode != 0:
                self.execute_panel.finish_running()
                self.execute_panel.output_log.write_line(
                    f"Pipeline {module}/{pipeline_name} stopped: task '{task_name}' {step} "
                    f"failed (exit {returncode}). Remaining tasks not run."
                )
                self.execute_panel.set_status(
                    f"Pipeline {module}/{pipeline_name} failed at {task_name} (exit {returncode})"
                )
                return

        self.execute_panel.finish_running()
        self.execute_panel.output_log.write_line(f"Pipeline {module}/{pipeline_name}, finished")
        self.execute_panel.set_status(f"Pipeline {module}/{pipeline_name} succeeded ({len(task_names)} tasks)")

    def action_kill_task(self) -> None:
        """Abort the currently running task, if any."""
        if not self.execute_panel or not self.current_process or self.current_process.poll() is not None:
            return
        self.execution_cancelled = True
        self.execute_panel.set_status("Aborting...")
        self.current_process.terminate()

    async def action_rebuild_database(self) -> None:
        """Rescan Code_directory, regenerate model_flow.db.json/model_flow.pipelines.json/
        model_flow.lists.json, and refresh the browse view."""
        if not self.database or not self.engine or not self.lists or not self.execute_panel:
            return

        self.execute_panel.display = True
        if self.main_view:
            self.main_view.display = False
        self.execute_panel.start_running("Rebuilding task database...")
        self.execute_panel.output_log.clear()

        code_directory = self.config.get("Code_directory")

        # parse_modules/parse_pipelines/parse_lists run on a worker thread, so each
        # on_file callback must marshal back to the UI thread via call_from_thread,
        # same as ExecutionEngine's on_output during task execution.
        def on_file(path: str) -> None:
            self.call_from_thread(self.execute_panel.append_output, f"Scanning: {path}")

        try:
            modules = await asyncio.to_thread(Parser.parse_modules, code_directory, on_file)
            pipelines = await asyncio.to_thread(Parser.parse_pipelines, code_directory, modules, on_file)
            lists = await asyncio.to_thread(Parser.parse_lists, code_directory, on_file)
        except Exception as e:
            self.execute_panel.show_error("build", "model_flow.db.json", str(e))
            return

        # Update both this app's Database/Lists and the ExecutionEngine's own
        # (separate) Database instance, so subsequent executions use the
        # freshly-scanned tasks too.
        self.database.data = modules
        self.database.save()
        self.database.pipelines_data = pipelines
        self.database.save_pipelines()
        self.lists.lists_data = lists
        self.lists.save()
        self.engine.database.data = modules
        self.engine.database.pipelines_data = pipelines

        module_count = len(modules)
        task_count = sum(len(tasks) for tasks in modules.values())
        pipeline_count = sum(len(p) for p in pipelines.values())
        list_count = len(lists)
        summary = (
            f"Database rebuilt: {module_count} modules, {task_count} tasks, "
            f"{pipeline_count} pipelines, {list_count} lists"
        )
        self.execute_panel.output_log.write("\n\n"+summary)
        self.execute_panel.finish_running()
        self.execute_panel.set_status(summary)

        self.query_one(SelectTask).refresh_from_database()




if __name__ == "__main__":
    app = ModelFlowApp()
    app.run()
