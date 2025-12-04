"""Custom widgets for the Jet TUI."""
from textual.widgets import DataTable, Static, RichLog, Input
from textual.reactive import reactive
from textual import events
from rich.text import Text
from rich.style import Style
from typing import Optional, Callable, Any


class ResourceTable(DataTable):
    """A DataTable with k9s-style keybindings and selection behavior."""
    
    BINDINGS = [
        ("k", "cursor_up", "Up"),
        ("K", "cursor_up", "Up"),
        ("j", "cursor_down", "Down"),
        ("J", "cursor_down", "Down"),
        ("g", "scroll_top", "Top"),
        ("G", "scroll_bottom", "Bottom"),
    ]
    
    selected_row_data: reactive[Optional[Any]] = reactive(None)
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cursor_type = "row"
        self.zebra_stripes = True
    
    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection."""
        if event.row_key is not None:
            self.selected_row_data = event.row_key.value
    
    def action_scroll_top(self) -> None:
        """Move cursor to top."""
        if self.row_count > 0:
            self.move_cursor(row=0)
    
    def action_scroll_bottom(self) -> None:
        """Move cursor to bottom."""
        if self.row_count > 0:
            self.move_cursor(row=self.row_count - 1)
    
    def get_selected_row_key(self) -> Optional[str]:
        """Get the key of the currently selected row."""
        if self.cursor_row is not None and self.cursor_row < self.row_count:
            row_key = self.get_row_at(self.cursor_row)
            return str(row_key) if row_key else None
        return None


class HeaderBar(Static):
    """Header bar showing current context and resource count."""
    
    title: reactive[str] = reactive("")
    count: reactive[int] = reactive(0)
    filter_text: reactive[str] = reactive("")
    
    def render(self) -> Text:
        """Render the header."""
        title_text = self.title
        if self.filter_text:
            title_text += f" <{self.filter_text}>"
        
        header = Text()
        header.append("┌", style="bold cyan")
        header.append("─" * 20, style="cyan")
        header.append(f" {title_text}[{self.count}] ", style="bold white")
        header.append("─" * 20, style="cyan")
        header.append("┐", style="bold cyan")
        
        return header


class FooterBar(Static):
    """Footer bar showing keybindings."""
    
    DEFAULT_CSS = """
    FooterBar {
        dock: bottom;
        height: 1;
        background: $surface;
    }
    """
    
    keybindings: reactive[list] = reactive([])
    
    def __init__(self, bindings: list = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.keybindings = bindings or []
    
    def render(self) -> Text:
        """Render the footer."""
        footer = Text()
        
        for i, (key, action) in enumerate(self.keybindings):
            if i > 0:
                footer.append(" │ ", style="dim")
            footer.append(f"<{key}>", style="bold cyan")
            footer.append(f" {action}", style="dim white")
        
        return footer


class StatusIndicator(Static):
    """Status indicator with colored dot."""
    
    status: reactive[str] = reactive("Unknown")
    
    STATUS_COLORS = {
        "Running": "green",
        "Succeeded": "green",
        "Complete": "green",
        "Completed": "green",
        "Pending": "yellow",
        "ContainerCreating": "yellow",
        "PodInitializing": "yellow",
        "Failed": "red",
        "Error": "red",
        "CrashLoopBackOff": "red",
        "ImagePullBackOff": "red",
        "ErrImagePull": "red",
        "OOMKilled": "red",
        "Terminating": "magenta",
        "Unknown": "dim white",
    }
    
    def render(self) -> Text:
        """Render the status indicator."""
        color = self.STATUS_COLORS.get(self.status, "dim white")
        return Text(f"● {self.status}", style=color)


class ScrollableLog(RichLog):
    """A scrollable log viewer with search capability."""
    
    BINDINGS = [
        ("k", "scroll_up", "Scroll Up"),
        ("j", "scroll_down", "Scroll Down"),
        ("g", "scroll_home", "Top"),
        ("G", "scroll_end", "Bottom"),
        ("f", "page_down", "Page Down"),
        ("b", "page_up", "Page Up"),
    ]
    
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('highlight', True)
        kwargs.setdefault('markup', True)
        kwargs.setdefault('wrap', False)
        super().__init__(*args, **kwargs)


class FooterPromptInput(Input):
    """Input widget that notifies parent when Enter/Escape is pressed."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cancel_handler: Optional[Callable[[], None]] = None
        self.submit_handler: Optional[Callable[[str], None]] = None
        self.change_handler: Optional[Callable[[str], None]] = None

    def _on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            event.stop()
            if self.cancel_handler:
                self.cancel_handler()
            return
        if event.key in ("enter", "return"):
            event.stop()
            if self.submit_handler:
                self.submit_handler(self.value)
            return
        return super()._on_key(event)
    
    def watch_value(self, value: str) -> None:
        """Called when value changes - notify change handler."""
        if self.change_handler:
            self.change_handler(value)
