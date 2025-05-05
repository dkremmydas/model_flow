from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static, Tree, Log, Select, Footer

from classes.Database import Database


class ModelFlowApp(App):
    """A Textual-based GUI for the Model Flow application."""

    CSS_PATH = "styles/app.css"  # Optional: Define a CSS file for styling

    def __init__(self, config=None) -> None:
        """Initialize the application."""
        super().__init__()
        self.config = config  # Store the configuration if needed
        self.database = Database(config)
        self.modules = self.database.list_modules()  # Load the list of modules from the database
        self.module_tasks = {module: self.database.list_module_tasks(module) for module in self.modules}
        print(self.modules)
        print(self.module_tasks)
        

    def compose(self) -> ComposeResult:
        """Compose the layout of the application."""
        # Row 1: Static text
        yield Horizontal(
           Static(
            f"Model Flow Application. Config file from {self.config.get('database_directory', 'Not specified')}",
            id="header-row"
            )
        )


        # Row 2: Module selector
        yield Horizontal(
            Static("Select Module:", id="module-label"),
            Select(
            options=[(module, module) for module in self.modules],
            id="module-selector",
            ),
            id="module-row",
        )

        # Row 3: Main content (Tree and Output)
        yield Horizontal(
            Tree("Modules and Tasks", id="tree-view"),
            Log(id="output-view"),  # Replace TextLog with Log
            id="main-content",
        )

        # Row 4: Footer
        yield Footer()

    def on_mount(self) -> None:
        """Initialize the application when it starts."""
        # Populate the tree view with modules and tasks from the database
        tree = self.query_one("#tree-view", Tree)
        root = tree.root

        for module, tasks in self.module_tasks.items():
            module_node = root.add(module)
            for task in tasks:
                module_node.add(task)

        root.expand()

    def on_select_changed(self, event: Select.Changed) -> None:
        """Handle module selection changes."""
        selected_module = event.value
        output_view = self.query_one("#output-view", Log)
        output_view.write(f"Selected module: {selected_module}")

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        """Handle tree node selection."""
        selected_node = event.node
        output_view = self.query_one("#output-view", Log)
        output_view.write(f"Selected task: {selected_node.label}")


if __name__ == "__main__":
    app = ModelFlowApp()
    app.run()