from textual.widget import Widget


class Header(Widget):
    """A custom header widget for the Model Flow application."""

    def render(self) -> str:
        """Render the header content."""
        return "Model Flow Application - Manage Your Tasks and Pipelines"