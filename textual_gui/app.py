from textual.app import App, ComposeResult, Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Static, Tree, Log, Select, Footer, Header, Input
from textual.widget import Widget
from textual.widgets import DataTable

from classes.Config import Config
from classes.Database import Database
from classes.Task import Task



class SelectTask(Widget):    
    
    tree = None  # Reactive attribute to hold the tree widget
    
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
    
    
    def __init__(self, database: Database) -> None:
        super().__init__(id= "select-task")
        self.database = database
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
        root = self.tree.root

        for module, tasks in self.module_tasks.items():
            module_node = root.add(module)
            for task in tasks:
                module_node.add(task)
            module_node.expand()
        root.expand()

    # def on_select_changed(self, event: Select.Changed) -> None:
    #     """Handle module selection changes."""
    #     selected_module = event.value
    #     output_view = super.query_one("#output-view", Log)
    #     output_view.write(f"Selected module: {selected_module}")

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        """Handle tree node selection."""
        selected_node = event.node
        output_view = super.query_one("task-log", Log)
        output_view.write(f"Selected task: {selected_node.label}")
        




class ShowTask(Widget):
    
    task = None  # Reactive attribute to hold the selected task
    
    DEFAULT_CSS = """
    ShowTask {
        layout: vertical;
        width: 49%;
        border: solid red;
        margin: 1;
        padding: 1;
    }
    """
    
    def __init__(self, task: Task) -> None: 
        """Initialize the application."""
        super().__init__(id= "show-task")
        
    def compose(self) -> ComposeResult:
        """Compose the layout of the application."""
        with Vertical():
            yield Log(id="task-log")  # Replace TextLog with Log
        
    
    def set_task(self, task: Task) -> None:
        """Update the task when it changes."""
        if task:
            # Update the task and print its details to the task-log
            self.task = task
            task_log = self.query_one("#task-log", Log)
            task_log.clear()  # Clear previous task details
            task.print(task_log.write)
            pass        
            
        



class ExecuteTask(Widget):
    
    def __init__(self, task: Task) -> None: 
        """Initialize the application."""
        super().__init__()
        self.task = task        
        




class ModelFlowApp(App):
    """A Textual-based GUI for the Model Flow application."""

    DEFAULT_CSS = """
        Screen {
            background: black;
            color: white;
            layout: vertical;
        }
    """
    
    
    BINDINGS = [
        ("escape", "quit", "Quit")
    ]


    def __init__(self, config: Config = None) -> None:
        """Initialize the application."""
        super().__init__()
        self.config = config  # Store the configuration if needed    
        self.title = f"Model Flow - Database Directory: {self.config.get("database_directory", "Not specified")}"
        

    def compose(self) -> ComposeResult:
        """Compose the layout of the application."""
        
        # Row 1: Static text
        yield Header()
        yield Horizontal(
            SelectTask(Database(self.config)),          
            ShowTask(None),
            id="container"
        )     
        yield Footer()



if __name__ == "__main__":
    app = ModelFlowApp()
    app.run()