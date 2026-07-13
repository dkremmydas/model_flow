import asyncio
import re

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static, Tree, Log, Select, Footer, Header, Input
from textual.widget import Widget
from textual.widgets.tree import TreeNode

from rich.text import Text

from classes.Config import Config
from classes.Database import Database
from classes.ExecutionEngine import ExecutionEngine, ExecutionResult
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
        self.tree = Tree("Modules and Tasks", id="tree-view")


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
            module_matches = query in module.lower()
            matching_tasks = tasks if module_matches else [t for t in tasks if query in t.lower()]
            if module_matches or matching_tasks:
                module_node = root.add(module)
                for task in matching_tasks:
                    module_node.add(task)
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
    """

    def __init__(self, modelflowapp: "ModelFlowApp") -> None:
        """Initialize the widget."""
        super().__init__(id="show-task")
        self.modelflowapp = modelflowapp
        # Named task_tree/description_log (not tree/log) to avoid colliding with
        # Widget's own built-in `tree`/`log` devtools properties (no setter).
        self.task_tree = Tree("Select a task", id="task-log")
        self.description_log = Log(id="description")
        self.description_log.auto_scroll = False
        self.config_editor = Vertical(id="config-editor")
        self.current_task = None

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

    async def show_task(self, task: dict) -> None:
        """Update the task in the ShowTask widget."""
        self.current_task = task

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
        ("ctrl+r", "execute_task", "Execute Task"),
        ("ctrl+k", "kill_task", "Abort Task"),
        ("ctrl+o", "toggle_output", "Toggle Output"),
        ("ctrl+b", "rebuild_database", "Rebuild DB"),
    ]



    def __init__(self, config: Config = None) -> None:
        """Initialize the application."""
        super().__init__()
        self.config = config  # Store the configuration if needed
        self.database = None
        self.engine = None
        self.execute_panel = None
        self.main_view = None
        self.selected_task = None  # (module, task_name) of the currently selected task
        self.startup_error = None
        self.current_process = None  # subprocess.Popen of the task currently running, if any
        self.execution_cancelled = False  # set just before terminating current_process

        try:
            self.database = Database(self.config)
            self.engine = ExecutionEngine(self.config)
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
        """Update the task in the ShowTask widget."""
        task_name = str(node.label)
        module_name = None if str(node.parent.label) == 'Modules and Tasks' else str(node.parent.label)

        if not module_name:
            return

        task = self.database.get_task(module_name, task_name)
        if not task:
            return

        self.selected_task = (module_name, task_name)
        show_task_widget = self.query_one("#show-task", ShowTask)
        await show_task_widget.show_task(task)

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

    def action_kill_task(self) -> None:
        """Abort the currently running task, if any."""
        if not self.execute_panel or not self.current_process or self.current_process.poll() is not None:
            return
        self.execution_cancelled = True
        self.execute_panel.set_status("Aborting...")
        self.current_process.terminate()

    async def action_rebuild_database(self) -> None:
        """Rescan Code_directory, regenerate model_flow.db.json, and refresh the browse view."""
        if not self.database or not self.engine or not self.execute_panel:
            return

        self.execute_panel.display = True
        if self.main_view:
            self.main_view.display = False
        self.execute_panel.start_running("Rebuilding task database...")
        self.execute_panel.output_log.clear()

        code_directory = self.config.get("Code_directory")

        try:
            modules = await asyncio.to_thread(Parser.parse_modules, code_directory)
        except Exception as e:
            self.execute_panel.show_error("build", "model_flow.db.json", str(e))
            return

        # Update both this app's Database and the ExecutionEngine's own (separate) instance,
        # so subsequent executions use the freshly-scanned tasks too.
        self.database.data = modules
        self.database.save()
        self.engine.database.data = modules

        module_count = len(modules)
        task_count = sum(len(tasks) for tasks in modules.values())
        self.execute_panel.output_log.write(f"Scanned: {code_directory}\n")
        self.execute_panel.finish_running()
        self.execute_panel.set_status(f"Database rebuilt: {module_count} modules, {task_count} tasks")

        self.query_one(SelectTask).refresh_from_database()




if __name__ == "__main__":
    app = ModelFlowApp()
    app.run()
