from textual.widgets import Static, Select
from textual.containers import Horizontal


class ModuleSelector(Horizontal):
    """A custom widget for selecting a module."""

    def __init__(self, *args, **kwargs):
        """Initialize the ModuleSelector widget."""
        super().__init__(*args, **kwargs)
        self.module_label = Static("Select Module:", id="module-label")
        self.module_select = Select(id="module-selector")

    def compose(self):
        """Compose the module selector layout."""
        yield self.module_label
        yield self.module_select

    def populate_modules(self, modules):
        """
        Populate the module selector with a list of modules.

        Parameters:
            modules (list of tuple): A list of (display_name, value) tuples.
        """
        self.module_select.options = modules