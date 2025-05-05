from textual.widgets import Tree
from textual.containers import Vertical


class TreeView(Vertical):
    """A custom widget for displaying a tree of modules and tasks."""

    def __init__(self, *args, **kwargs):
        """Initialize the TreeView widget."""
        super().__init__(*args, **kwargs)
        self.tree = Tree("Modules and Tasks", id="tree-view")

    def compose(self):
        """Compose the tree view layout."""
        yield self.tree

    def populate_tree(self, data):
        """
        Populate the tree with modules and tasks.

        Parameters:
            data (dict): A dictionary where keys are module names and values are lists of task names.
        """
        root = self.tree.root
        root.clear()  # Clear any existing nodes

        for module_name, tasks in data.items():
            module_node = root.add(module_name)
            for task_name in tasks:
                module_node.add(task_name)

        root.expand()  # Expand the root node to show all modules and tasks