from textual.app import App, ComposeResult, Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Static, Tree, Log, Select, Footer, Header, Input
from textual.widget import Widget
from textual.widgets import DataTable
from textual.widgets.tree import TreeNode

from rich.text import Text

from classes.Config import Config
from classes.Database import Database
from classes.Task import Task
import json



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
        root = self.tree.root

        for module, tasks in self.module_tasks.items():
            module_node = root.add(module)
            for task in tasks:
                module_node.add(task)
            #module_node.expand()
        root.expand()

    # def on_select_changed(self, event: Select.Changed) -> None:
    #     """Handle module selection changes."""
    #     selected_module = event.value
    #     output_view = super.query_one("#output-view", Log)
    #     output_view.write(f"Selected module: {selected_module}")

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        """Handle tree node selection."""
        selected_node = event.node
        self.modelflowapp.show_task(selected_node)  # Call the method in ModelFlowApp to update the task
       




class ShowTask(Widget):
    
    tree = Tree("Select a task",id="task-log") 
    #log = Log(id="debug-log")
    
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
            yield self.tree
            #yield self.log
            
    def show_task(self, task: Task) -> None:
        """Update the task in the ShowTask widget."""
        self.tree.clear()        
        #self.log.write_line(json.dumps(task, indent=2))
        
        # Convert the task object to a dictionary, excluding 'configarray'
        task_new = task.copy()
        del(task_new["config"])
        del(task_new["description"])
        del(task_new["module"])
        del(task_new["name"])
        config_dict = {item["name"]: {k: v for k, v in item.items() if k != "name"} for item in task["config"]}
        task_new["config"] = config_dict
        #self.log.write_line(json.dumps(config_dict, indent=2))

        self.add_json(Text(f"{task.get('module', '')}/{task.get('name', '')}"), self.tree.root, task_new)

        
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
        self.database = Database(self.config)  # Initialize the database
        self.title = f"Model Flow - Database Directory: {self.config.get("database_directory", "Not specified")}"
        

    def compose(self) -> ComposeResult:
        """Compose the layout of the application."""
        
        # Row 1: Static text
        yield Header()
        yield Horizontal(
            SelectTask(self),          
            ShowTask(None),
            id="container"
        )     
        yield Footer()
        
    def show_task(self, node) -> None:
        """Update the task in the ShowTask widget."""
        task_name = str(node.label)
        module_name = None if str(node.parent.label) == 'Modules and Tasks' else str(node.parent.label)
        log = self.query_one("#show-task", ShowTask)

        if module_name:
            task = self.database.get_task(module_name, task_name)
            log.show_task(task)
            
     
    



if __name__ == "__main__":
    app = ModelFlowApp()
    app.run()