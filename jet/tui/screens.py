"""Screen implementations for Jet TUI."""
from textual.screen import Screen
from textual.app import ComposeResult
from textual.widgets import Static, DataTable, RichLog, LoadingIndicator, Footer
from textual.containers import Container, Vertical, Horizontal, VerticalScroll
from textual.binding import Binding
from textual.reactive import reactive
from textual import work
from textual.worker import get_current_worker
from rich.text import Text
from rich.style import Style
from typing import Optional, List, Callable
import asyncio
import os
from datetime import datetime

from .k8s import K8sClient, JobInfo, PodInfo, format_age, format_duration
from .k8s_watch import Kr8sWatcher
from .widgets import FooterPromptInput
from ..utils import get_current_namespace


class BaseListScreen(Screen):
    """Base screen for listing resources."""
    
    BINDINGS = [
        Binding("q", "quit", "Quit", show=True, priority=True),
        Binding("Q", "quit", "Quit", show=False, priority=True),
        Binding("escape", "go_back", "Back", show=True, priority=True),
        Binding("/", "search", "Search", show=True),
        Binding("r", "refresh", "Refresh", show=True),
        Binding("R", "refresh", "Refresh", show=False),
        Binding("d", "describe", "Describe", show=True),
        Binding("D", "describe", "Describe", show=False),
        Binding("l", "logs", "Logs", show=True),
        Binding("L", "logs", "Logs", show=False),
        Binding("ctrl+c", "quit", "Quit", show=False, priority=True),
        Binding("ctrl+C", "quit", "Quit", show=False, priority=True),
    ]
    
    namespace: reactive[str] = reactive("")
    filter_text: reactive[str] = reactive("")
    resource_count: reactive[int] = reactive(0)
    
    def __init__(self, namespace: Optional[str] = None, initial_filter: Optional[str] = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.namespace = namespace or get_current_namespace()
        self.k8s = K8sClient(namespace=self.namespace)  # Keep for describe/delete operations
        self.watcher = Kr8sWatcher(namespace=self.namespace)
        self._restore_cursor: Optional[int] = None  # Cursor to restore after returning from logs
        self._age_timer = None  # Timer for refreshing age display
        self._footer_prompt_callback: Optional[Callable[[int], None]] = None
        self._search_active: bool = False  # Track if search input is active
        self._watch_worker = None  # Track our own watch worker
        if initial_filter:
            self.filter_text = initial_filter
    
    def compose(self) -> ComposeResult:
        """Compose the screen layout."""
        yield Static(id="header")
        yield Container(
            DataTable(id="resource-table"),
            id="content"
        )
        yield Footer(id="footer")
        yield FooterPromptInput(id="footer-input", placeholder="", classes="footer-input")
    
    def on_mount(self) -> None:
        """Set up the screen on mount."""
        table = self.query_one("#resource-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = False
        table.cursor_foreground_priority = "renderable"  # Preserve Rich text colors on cursor row
        self._setup_columns(table)
        # Start the watch worker (cursor restoration happens in _update_table)
        self._start_watch()
        # Start timer to refresh age display every 2 seconds (no API calls, just recalculates from cached data)
        self._age_timer = self.set_interval(2.0, self._refresh_ages)
        footer_input = self.query_one("#footer-input", FooterPromptInput)
        footer_input.display = False
    
    def on_screen_resume(self) -> None:
        """Called when screen becomes active again after being revealed by pop_screen."""
        # Check if our specific watch worker is still running
        worker_running = self._watch_worker is not None and self._watch_worker.is_running
        
        # Restart the watch only if our worker is not running
        if not worker_running:
            self._start_watch()
        # Restart age timer if not running
        if self._age_timer is None:
            self._age_timer = self.set_interval(2.0, self._refresh_ages)
    
    def on_screen_suspend(self) -> None:
        """Called when another screen is pushed on top."""
        # Don't cancel workers or change state - let watch continue running
        # But stop the age timer to avoid unnecessary updates
        if self._age_timer is not None:
            self._age_timer.stop()
            self._age_timer = None
    
    def on_unmount(self) -> None:
        """Clean up when screen is unmounted."""
        # Cancel only our own watch worker, not all workers
        if self._watch_worker is not None:
            self._watch_worker.cancel()
            self._watch_worker = None
        # Stop age timer
        if self._age_timer is not None:
            self._age_timer.stop()
            self._age_timer = None
    
    def on_resize(self, event) -> None:
        """Handle terminal resize - update header and recalculate table columns."""
        self._update_header()
        self._resize_table_columns()
    
    def _resize_table_columns(self) -> None:
        """Recalculate and update table column widths on resize. Override in subclass."""
        pass
    
    def _setup_columns(self, table: DataTable) -> None:
        """Override to set up table columns."""
        pass
    
    def _start_watch(self) -> None:
        """Start the watch worker. Override in subclass."""
        pass
    
    def _refresh_ages(self) -> None:
        """Refresh age column from cached data. Override in subclass."""
        pass
    
    def _update_header(self) -> None:
        """Update the header with current info."""
        pass
    
    def action_go_back(self) -> None:
        """Go back to previous screen or quit if at root.
        
        Priority:
        1. If search input is active -> close search input
        2. If filter is active (not in search) -> clear filter
        3. Otherwise -> go back to previous screen or exit
        """
        # First priority: close search input if active
        if self._search_active:
            self._close_search_prompt()
            return
        
        # Second priority: close other prompts (like line count)
        if self._is_prompt_active():
            self._hide_footer_prompt()
            return
        
        # Third priority: clear filter if active
        if self.filter_text:
            self.filter_text = ""
            self._apply_filter()
            self._update_header()
            return
        
        # Finally: go back or exit
        # NOTE: Don't cancel workers here - on_unmount will handle cleanup.
        # Cancelling here would cancel workers from OTHER screens too since
        # Textual workers are app-level, not screen-level.
        
        # Check if we can go back or should exit
        # screen_stack includes the default screen, so check for <= 2
        if len(self.app.screen_stack) <= 2:
            self.app.exit()
        else:
            self.app.pop_screen()
    
    def action_quit(self) -> None:
        """Quit the application."""
        self.workers.cancel_all()
        self.app.exit()
    
    def action_search(self) -> None:
        """Show search input for filtering resources."""
        if self._is_prompt_active():
            return
        self._show_search_prompt()
    
    def _show_search_prompt(self) -> None:
        """Show the search input prompt."""
        if self._search_active or self._is_prompt_active():
            return
        self._search_active = True
        footer = self.query_one("#footer", Footer)
        footer_input = self.query_one("#footer-input", FooterPromptInput)
        footer.display = False
        footer_input.display = True
        footer_input.placeholder = "Filter by name (Esc to close)"
        footer_input.value = self.filter_text  # Start with current filter
        footer_input.cancel_handler = self._close_search_prompt
        footer_input.submit_handler = self._close_search_prompt_with_value
        footer_input.change_handler = self._on_search_change  # Real-time filtering
        footer_input.focus()
        self.set_focus(footer_input)
        self.call_after_refresh(lambda: footer_input.focus())
    
    def _close_search_prompt(self) -> None:
        """Close search prompt, keeping current filter."""
        self._search_active = False
        footer = self.query_one("#footer", Footer)
        footer_input = self.query_one("#footer-input", FooterPromptInput)
        footer_input.display = False
        footer_input.cancel_handler = None
        footer_input.submit_handler = None
        footer_input.change_handler = None
        footer.display = True
        try:
            table = self.query_one("#resource-table", DataTable)
            table.focus()
        except Exception:
            pass
    
    def _close_search_prompt_with_value(self, value: str) -> None:
        """Close search prompt (Enter pressed), filter is already applied."""
        self._close_search_prompt()
    
    def _on_search_change(self, value: str) -> None:
        """Called when search input changes - filter in real-time."""
        self.filter_text = value.strip().lower()
        self._apply_filter()
    
    def _apply_filter(self) -> None:
        """Apply filter to table. Override in subclass."""
        pass
    
    def action_refresh(self) -> None:
        """Manually refresh - restarts the watch."""
        # Cancel our own watch worker and restart
        if self._watch_worker is not None:
            self._watch_worker.cancel()
            self._watch_worker = None
        self._start_watch()
    
    def action_describe(self) -> None:
        """Show describe for selected resource."""
        pass
    
    def action_logs(self) -> None:
        """Show logs for selected resource."""
        pass

    def _is_prompt_active(self) -> bool:
        return self._footer_prompt_callback is not None

    def _show_footer_prompt(self, prompt: str, callback: Callable[[int], None]) -> None:
        if self._is_prompt_active():
            return
        footer = self.query_one("#footer", Footer)
        footer_input = self.query_one("#footer-input", FooterPromptInput)
        self._footer_prompt_callback = callback
        footer.display = False
        footer_input.display = True
        footer_input.submitted = False
        footer_input.placeholder = prompt
        footer_input.value = ""
        footer_input.cancel_handler = self._hide_footer_prompt
        footer_input.submit_handler = self._process_footer_input
        footer_input.focus()
        self.set_focus(footer_input)
        self.call_after_refresh(lambda: footer_input.focus())

    def _hide_footer_prompt(self) -> None:
        footer = self.query_one("#footer", Footer)
        footer_input = self.query_one("#footer-input", FooterPromptInput)
        footer_input.value = ""
        footer_input.display = False
        footer_input.cancel_handler = None
        footer_input.submit_handler = None
        footer_input.change_handler = None
        footer.display = True
        self._footer_prompt_callback = None
        try:
            table = self.query_one("#resource-table", DataTable)
            table.focus()
        except Exception:
            pass

    def _parse_line_count(self, raw_value: str) -> int:
        default_count = 50
        value = raw_value.strip()
        if not value:
            return default_count
        try:
            count = int(value)
            return count if count > 0 else default_count
        except ValueError:
            return default_count

    def _process_footer_input(self, value: str) -> None:
        callback = self._footer_prompt_callback
        self._hide_footer_prompt()
        if callback:
            callback(self._parse_line_count(value))

    
    def _get_selected_name(self) -> Optional[str]:
        """Get the name of the selected resource."""
        table = self.query_one("#resource-table", DataTable)
        if table.cursor_row is not None and table.row_count > 0:
            row_key = table.get_row_at(table.cursor_row)
            if row_key:
                return str(row_key)
        return None


class JobsScreen(BaseListScreen):
    """Screen for listing Jobs."""
    
    BINDINGS = [
        Binding("q", "quit", "Quit", show=True, priority=True),
        Binding("Q", "quit", "Quit", show=False, priority=True),
        Binding("escape", "go_back", "Back", show=True, priority=True),
        Binding("/", "search", "Search", show=True),
        Binding("enter", "select_job", "Pods", show=True, priority=True),
        Binding("p", "all_pods", "All Pods", show=True),
        Binding("P", "all_pods", "All Pods", show=False),
        Binding("r", "refresh", "Refresh", show=True),
        Binding("R", "refresh", "Refresh", show=False),
        Binding("d", "describe", "Describe", show=True),
        Binding("D", "describe", "Describe", show=False),
        Binding("l", "logs", "Logs", show=True),
        Binding("L", "logs", "Logs", show=False),
        Binding("t", "tail_logs", "Tail", show=True),
        Binding("T", "tail_logs", "Tail", show=False),
        Binding("h", "head_logs", "Head", show=True),
        Binding("H", "head_logs", "Head", show=False),
        Binding("x", "delete", "Delete", show=True),
        Binding("X", "delete", "Delete", show=False),
        Binding("ctrl+c", "quit", "Quit", show=False, priority=True),
        Binding("ctrl+C", "quit", "Quit", show=False, priority=True),
    ]
    
    def __init__(self, namespace: Optional[str] = None, initial_filter: Optional[str] = None, *args, **kwargs):
        super().__init__(namespace=namespace, initial_filter=initial_filter, *args, **kwargs)
        self.jobs: List[JobInfo] = []
    
    def _setup_columns(self, table: DataTable) -> None:
        """Set up job table columns with dynamic widths."""
        # Column headers and their base widths
        # Base width = header length + 2 margin, except for special columns
        self._col_order = ["NAME", "STATUS", "COMPLETIONS", "DURATION", "AGE↑"]
        self._base_col_widths = {
            "NAME": 6,        # "NAME" (4) + 2 margin, but will grow dynamically
            "STATUS": 8,      # "STATUS" (6) + 2, but will grow dynamically
            "COMPLETIONS": 13, # "COMPLETIONS" (11) + 2
            "DURATION": 10,    # "DURATION" (8) + 2 (content is short like "5s")
            "AGE↑": 5,        # "AGE↑" (4) + 1 (content like "5d")
        }
        # Track current dynamic column widths
        self._current_name_width = self._base_col_widths["NAME"]
        self._current_status_width = self._base_col_widths["STATUS"]
        
        widths = self._calculate_column_widths()
        for col_name in self._col_order:
            table.add_column(col_name, width=widths[col_name])
    
    def _calculate_column_widths(self) -> dict:
        """Calculate column widths, distributing space evenly."""
        try:
            screen_width = self.app.size.width
        except Exception:
            screen_width = 80
        
        num_cols = len(self._col_order)
        # Account for DataTable borders/padding and right margin
        overhead = 6 + num_cols
        usable_width = screen_width - overhead
        
        # Dynamic columns use their current widths, others use base widths
        dynamic_cols = {"NAME", "STATUS"}
        dynamic_total = self._current_name_width + self._current_status_width
        
        # Non-dynamic columns and their base widths
        non_dynamic_cols = [c for c in self._col_order if c not in dynamic_cols]
        non_dynamic_base = sum(self._base_col_widths[c] for c in non_dynamic_cols)
        
        # Total base width needed
        total_base = dynamic_total + non_dynamic_base
        
        widths = {}
        
        if usable_width >= total_base:
            # Enough space - distribute extra evenly, with remainder going to first columns
            extra = usable_width - total_base
            extra_per_col = extra // num_cols
            remainder = extra % num_cols
            
            for i, col in enumerate(self._col_order):
                if col in dynamic_cols:
                    base = self._current_name_width if col == "NAME" else self._current_status_width
                else:
                    base = self._base_col_widths[col]
                # Give +1 to first 'remainder' columns to use up all space
                widths[col] = base + extra_per_col + (1 if i < remainder else 0)
        else:
            # Not enough space - dynamic columns get their width, others get base
            widths["NAME"] = self._current_name_width
            widths["STATUS"] = self._current_status_width
            for col in non_dynamic_cols:
                widths[col] = self._base_col_widths[col]
        
        return widths
    
    def _update_name_column_width(self, names: List[str]) -> bool:
        """Update NAME column width based on current data. Returns True if width changed."""
        if not names:
            return False
        max_name_len = max(len(name) for name in names)
        needed_width = max(max_name_len + 2, self._base_col_widths["NAME"])  # At least base width
        
        if needed_width != self._current_name_width:
            self._current_name_width = needed_width
            return True
        return False
    
    def _update_status_column_width(self, statuses: List[str]) -> bool:
        """Update STATUS column width based on current data. Returns True if width changed."""
        if not statuses:
            return False
        max_status_len = max(len(status) for status in statuses)
        needed_width = max(max_status_len + 2, self._base_col_widths["STATUS"])  # At least base width
        
        if needed_width != self._current_status_width:
            self._current_status_width = needed_width
            return True
        return False
    
    def _update_header(self) -> None:
        """Update the header."""
        header = self.query_one("#header", Static)
        title = f"jobs({self.namespace})[{self.resource_count}]"
        
        # Build the center content first to calculate padding
        center_content = f" {title} "
        if self.filter_text:
            center_content += f"</{self.filter_text}> "
        
        # Get available width (terminal width minus corners and padding)
        try:
            total_width = self.app.size.width - 4  # Account for corners and some padding
        except Exception:
            total_width = 80  # Fallback
        
        # Calculate padding on each side
        center_len = len(center_content)
        remaining = max(0, total_width - center_len)
        left_pad = remaining // 2
        right_pad = remaining - left_pad
        
        header_text = Text()
        header_text.append("┌", style="bold cyan")
        header_text.append("─" * left_pad, style="cyan")
        header_text.append(f" {title} ", style="bold white")
        if self.filter_text:
            header_text.append("<", style="white")
            header_text.append(f"/{self.filter_text}", style="bold yellow on #333333")
            header_text.append(">", style="white")
            header_text.append(" ", style="")
        header_text.append("─" * right_pad, style="cyan")
        header_text.append("┐", style="bold cyan")
        
        header.update(header_text)
    
    def _start_watch(self) -> None:
        """Start the jobs watch worker."""
        self._watch_worker = self._watch_jobs()
    
    @work(exclusive=False)
    async def _watch_jobs(self) -> None:
        """Watch jobs and update table on changes."""
        try:
            async for jobs in self.watcher.watch_jobs():
                self._update_table(jobs)
        except asyncio.CancelledError:
            pass
        except Exception:
            pass
    
    def _update_table(self, jobs: List[JobInfo]) -> None:
        """Update the table with jobs data."""
        self.jobs = jobs
        
        # Filter jobs based on search text
        if self.filter_text:
            filtered_jobs = [j for j in jobs if self.filter_text in j.name.lower()]
        else:
            filtered_jobs = jobs
        
        self.resource_count = len(filtered_jobs)
        self._update_header()
        
        table = self.query_one("#resource-table", DataTable)
        
        # Check if NAME or STATUS columns need resizing based on current data
        job_names = [j.name for j in filtered_jobs]
        job_statuses = [j.status for j in filtered_jobs]
        name_changed = self._update_name_column_width(job_names)
        status_changed = self._update_status_column_width(job_statuses)
        if name_changed or status_changed:
            self._resize_table_columns()
        
        # Save cursor position BEFORE clearing (clear resets cursor to 0)
        current_cursor = table.cursor_row if table.row_count > 0 else 0
        
        # Determine target row: prefer restore cursor, then saved current position
        if self._restore_cursor is not None:
            target_row = self._restore_cursor
        else:
            target_row = current_cursor
        
        # Clear and repopulate
        table.clear()
        
        for job in filtered_jobs:
            # Color status
            status_style = self._get_status_style(job.status)
            status_text = Text(job.status, style=status_style)
            
            table.add_row(
                job.name,
                status_text,
                job.completions,
                job.duration,
                job.age,
                key=job.name
            )
        
        # Restore cursor to target position
        if table.row_count > 0 and target_row is not None:
            row = min(target_row, table.row_count - 1)
            table.move_cursor(row=row)
            if self._restore_cursor is not None and table.row_count > self._restore_cursor:
                self._restore_cursor = None
    
    def _apply_filter(self) -> None:
        """Re-apply filter to current data."""
        if self.jobs:
            self._update_table(self.jobs)
    
    def _get_status_style(self, status: str) -> Style:
        """Get style for status."""
        status_colors = {
            "Running": "green",
            "Complete": "green",
            "Succeeded": "green",
            "Pending": "yellow",
            "Suspended": "yellow",
            "Failed": "red",
            "Deleting": "magenta",
        }
        color = status_colors.get(status, "white")
        return Style(color=color)
    
    def _refresh_ages(self) -> None:
        """Refresh age and duration columns from cached job data (no API calls)."""
        try:
            if not self.jobs:
                return
            table = self.query_one("#resource-table", DataTable)
            if table.row_count == 0:
                return  # Table not ready yet
            columns = list(table.columns.keys())
            if len(columns) < 5:
                return
            duration_column_key = columns[3]  # DURATION is index 3
            age_column_key = columns[4]  # AGE is index 4
            for job in self.jobs:
                try:
                    # Recalculate age from stored created_at timestamp
                    new_age = format_age(job.created_at)
                    table.update_cell(job.name, age_column_key, new_age)
                    
                    # Update duration only for non-terminal jobs (still running)
                    if job.completion_time is None and job.start_time is not None:
                        new_duration = format_duration(job.start_time, None)
                        table.update_cell(job.name, duration_column_key, new_duration)
                except Exception:
                    pass  # Row may not exist yet
        except Exception:
            pass  # Table not ready
    
    def action_select_job(self) -> None:
        """Select job to view its pods."""
        if self._is_prompt_active():
            footer_input = self.query_one("#footer-input", FooterPromptInput)
            self._process_footer_input(footer_input.value)
            return
        if self._search_active:
            self._close_search_prompt()
            return
        job_name = self._get_selected_name()
        if job_name:
            table = self.query_one("#resource-table", DataTable)
            self.app.push_screen(PodsScreen(
                namespace=self.namespace,
                job_name=job_name,
                jobs_cursor_row=table.cursor_row,  # Pass current cursor for restoration
                jobs_filter=self.filter_text,  # Pass current filter for restoration
            ))
    
    def action_describe(self) -> None:
        """Show describe for selected job."""
        job_name = self._get_selected_name()
        if job_name:
            self.app.push_screen(DescribeScreen(
                resource_type="job",
                resource_name=job_name,
                namespace=self.namespace
            ))
    
    def action_logs(self) -> None:
        """Show logs for all pods of selected job - exits TUI to native terminal."""
        job_name = self._get_selected_name()
        if job_name:
            state = self._build_jobs_state()
            self.app.exit(result=("logs", "job", job_name, self.namespace, state, job_name))

    def action_tail_logs(self) -> None:
        """Prompt for tail line count and stream job logs."""
        job_name = self._get_selected_name()
        if job_name:
            self._show_footer_prompt(
                "Tail lines (default 50). Press Enter for default.",
                lambda count, name=job_name: self._start_tail_logs(name, count)
            )

    def action_head_logs(self) -> None:
        """Prompt for head line count and print job logs."""
        job_name = self._get_selected_name()
        if job_name:
            self._show_footer_prompt(
                "Head lines (default 50). Press Enter for default.",
                lambda count, name=job_name: self._start_head_logs(name, count)
            )

    def _build_jobs_state(self) -> dict:
        table = self.query_one("#resource-table", DataTable)
        return {
            "screen": "jobs",
            "namespace": self.namespace,
            "cursor_row": table.cursor_row or 0,
            "filter_text": self.filter_text,
        }

    def _start_tail_logs(self, job_name: str, line_count: int) -> None:
        state = self._build_jobs_state()
        self.app.exit(result=("logs_tail", "job", job_name, self.namespace, line_count, state, job_name))

    def _start_head_logs(self, job_name: str, line_count: int) -> None:
        state = self._build_jobs_state()
        self.app.exit(result=("logs_head", "job", job_name, self.namespace, line_count, state, job_name))
    
    def action_delete(self) -> None:
        """Delete selected job."""
        job_name = self._get_selected_name()
        if job_name:
            self.app.push_screen(ConfirmDeleteScreen(
                resource_type="job",
                resource_name=job_name,
                namespace=self.namespace
            ))
    
    def action_all_pods(self) -> None:
        """Go to all pods view."""
        self.app.push_screen(PodsScreen(namespace=self.namespace))
    
    def _resize_table_columns(self) -> None:
        """Recalculate all column widths on resize."""
        try:
            table = self.query_one("#resource-table", DataTable)
            if not hasattr(self, '_base_col_widths'):
                return
            widths = self._calculate_column_widths()
            columns = list(table.columns.keys())
            for i, col_key in enumerate(columns):
                col_name = self._col_order[i]
                table.columns[col_key].width = widths[col_name]
            table.refresh()
        except Exception:
            pass
    
    def _get_selected_name(self) -> Optional[str]:
        """Get the name of the selected job."""
        table = self.query_one("#resource-table", DataTable)
        if table.cursor_row is not None and table.row_count > 0:
            # Get the row data
            row_data = table.get_row_at(table.cursor_row)
            if row_data:
                # Name is the first column
                return str(table.get_cell_at((table.cursor_row, 0)))
        return None


class PodsScreen(BaseListScreen):
    """Screen for listing Pods."""
    
    BINDINGS = [
        Binding("q", "quit", "Quit", show=True, priority=True),
        Binding("Q", "quit", "Quit", show=False, priority=True),
        Binding("escape", "go_back", "Back", show=True, priority=True),
        Binding("/", "search", "Search", show=True),
        Binding("enter", "logs", "Logs", show=True, priority=True),
        Binding("j", "all_jobs", "All Jobs", show=True),
        Binding("J", "all_jobs", "All Jobs", show=False),
        Binding("r", "refresh", "Refresh", show=True),
        Binding("R", "refresh", "Refresh", show=False),
        Binding("d", "describe", "Describe", show=True),
        Binding("D", "describe", "Describe", show=False),
        Binding("l", "logs", "Logs", show=False),
        Binding("L", "logs", "Logs", show=False),
        Binding("t", "tail_logs", "Tail", show=True),
        Binding("T", "tail_logs", "Tail", show=False),
        Binding("h", "head_logs", "Head", show=True),
        Binding("H", "head_logs", "Head", show=False),
        Binding("x", "delete", "Delete", show=True),
        Binding("X", "delete", "Delete", show=False),
        Binding("s", "shell", "Shell", show=True),
        Binding("S", "shell", "Shell", show=False),
        Binding("ctrl+c", "quit", "Quit", show=False, priority=True),
        Binding("ctrl+C", "quit", "Quit", show=False, priority=True),
    ]
    
    def __init__(self, namespace: Optional[str] = None, job_name: Optional[str] = None, 
                 jobs_cursor_row: Optional[int] = None, jobs_filter: Optional[str] = None,
                 initial_filter: Optional[str] = None, *args, **kwargs):
        super().__init__(namespace=namespace, initial_filter=initial_filter, *args, **kwargs)
        self.job_name = job_name
        self.jobs_cursor_row = jobs_cursor_row  # Remember jobs screen cursor for restoration
        self.jobs_filter = jobs_filter  # Remember jobs screen filter for restoration
        self.pods: List[PodInfo] = []
    
    def _setup_columns(self, table: DataTable) -> None:
        """Set up pod table columns with dynamic widths."""
        # Column headers and their base widths
        # Base width = header length + 2 margin, except for special columns
        self._col_order = ["NAME↑", "READY", "STATUS", "RESTARTS", "IP", "NODE", "AGE"]
        self._base_col_widths = {
            "NAME↑": 6,       # "NAME↑" (5) + 1, but will grow dynamically
            "READY": 7,       # "READY" (5) + 2
            "STATUS": 8,      # "STATUS" (6) + 2, but will grow dynamically
            "RESTARTS": 10,   # "RESTARTS" (8) + 2
            "IP": 14,         # "IP" (2) + 2, but IPs are ~12 chars
            "NODE": 7,        # "NODE" (4) + 2, truncated to fit
            "AGE": 5,         # "AGE" (3) + 2
        }
        # Track current dynamic column widths
        self._current_name_width = self._base_col_widths["NAME↑"]
        self._current_status_width = self._base_col_widths["STATUS"]
        
        widths = self._calculate_column_widths()
        for col_name in self._col_order:
            table.add_column(col_name, width=widths[col_name])
    
    def _calculate_column_widths(self) -> dict:
        """Calculate column widths, distributing space evenly."""
        try:
            screen_width = self.app.size.width
        except Exception:
            screen_width = 80
        
        num_cols = len(self._col_order)
        # Account for DataTable borders/padding and right margin
        overhead = 6 + num_cols
        usable_width = screen_width - overhead
        
        # Dynamic columns use their current widths, others use base widths
        dynamic_cols = {"NAME↑", "STATUS"}
        dynamic_total = self._current_name_width + self._current_status_width
        
        # Non-dynamic columns and their base widths
        non_dynamic_cols = [c for c in self._col_order if c not in dynamic_cols]
        non_dynamic_base = sum(self._base_col_widths[c] for c in non_dynamic_cols)
        
        # Total base width needed
        total_base = dynamic_total + non_dynamic_base
        
        widths = {}
        
        if usable_width >= total_base:
            # Enough space - distribute extra evenly, with remainder going to first columns
            extra = usable_width - total_base
            extra_per_col = extra // num_cols
            remainder = extra % num_cols
            
            for i, col in enumerate(self._col_order):
                if col in dynamic_cols:
                    base = self._current_name_width if col == "NAME↑" else self._current_status_width
                else:
                    base = self._base_col_widths[col]
                # Give +1 to first 'remainder' columns to use up all space
                widths[col] = base + extra_per_col + (1 if i < remainder else 0)
        else:
            # Not enough space - dynamic columns get their width, others get base
            widths["NAME↑"] = self._current_name_width
            widths["STATUS"] = self._current_status_width
            for col in non_dynamic_cols:
                widths[col] = self._base_col_widths[col]
        
        return widths
    
    def _update_name_column_width(self, names: List[str]) -> bool:
        """Update NAME column width based on current data. Returns True if width changed."""
        if not names:
            return False
        max_name_len = max(len(name) for name in names)
        needed_width = max(max_name_len + 2, self._base_col_widths["NAME↑"])  # At least base width
        
        if needed_width != self._current_name_width:
            self._current_name_width = needed_width
            return True
        return False
    
    def _update_status_column_width(self, statuses: List[str]) -> bool:
        """Update STATUS column width based on current data. Returns True if width changed."""
        if not statuses:
            return False
        max_status_len = max(len(status) for status in statuses)
        needed_width = max(max_status_len + 2, self._base_col_widths["STATUS"])  # At least base width
        
        if needed_width != self._current_status_width:
            self._current_status_width = needed_width
            return True
        return False
    
    def _update_header(self) -> None:
        """Update the header."""
        header = self.query_one("#header", Static)
        
        if self.job_name:
            title = f"pods({self.namespace}/{self.job_name})[{self.resource_count}]"
        else:
            title = f"pods({self.namespace})[{self.resource_count}]"
        
        # Build the center content first to calculate padding
        center_content = f" {title} "
        if self.filter_text:
            center_content += f"</{self.filter_text}> "
        
        # Get available width (terminal width minus corners and padding)
        try:
            total_width = self.app.size.width - 4  # Account for corners and some padding
        except Exception:
            total_width = 80  # Fallback
        
        # Calculate padding on each side
        center_len = len(center_content)
        remaining = max(0, total_width - center_len)
        left_pad = remaining // 2
        right_pad = remaining - left_pad
        
        header_text = Text()
        header_text.append("┌", style="bold cyan")
        header_text.append("─" * left_pad, style="cyan")
        header_text.append(f" {title} ", style="bold white")
        if self.filter_text:
            header_text.append("<", style="white")
            header_text.append(f"/{self.filter_text}", style="bold yellow on #333333")
            header_text.append(">", style="white")
            header_text.append(" ", style="")
        header_text.append("─" * right_pad, style="cyan")
        header_text.append("┐", style="bold cyan")
        
        header.update(header_text)
    
    def _start_watch(self) -> None:
        """Start the pods watch worker."""
        self._watch_worker = self._watch_pods()
    
    @work(exclusive=False)
    async def _watch_pods(self) -> None:
        """Watch pods and update table on changes."""
        try:
            async for pods in self.watcher.watch_pods(self.job_name):
                self._update_table(pods)
        except asyncio.CancelledError:
            pass
        except Exception:
            pass
    
    def _update_table(self, pods: List[PodInfo]) -> None:
        """Update the table with pods data."""
        self.pods = pods
        
        # Filter pods based on search text
        if self.filter_text:
            filtered_pods = [p for p in pods if self.filter_text in p.name.lower()]
        else:
            filtered_pods = pods
        
        self.resource_count = len(filtered_pods)
        self._update_header()
        
        table = self.query_one("#resource-table", DataTable)
        
        # Check if NAME or STATUS columns need resizing based on current data
        pod_names = [p.name for p in filtered_pods]
        pod_statuses = [p.status for p in filtered_pods]
        name_changed = self._update_name_column_width(pod_names)
        status_changed = self._update_status_column_width(pod_statuses)
        if name_changed or status_changed:
            self._resize_table_columns()
        
        # Save cursor position BEFORE clearing (clear resets cursor to 0)
        current_cursor = table.cursor_row if table.row_count > 0 else 0
        
        # Determine target row: prefer restore cursor, then saved current position
        if self._restore_cursor is not None:
            target_row = self._restore_cursor
        else:
            target_row = current_cursor
        
        # Clear and repopulate
        table.clear()
        
        for pod in filtered_pods:
            # Color status
            status_style = self._get_status_style(pod.status)
            status_text = Text(pod.status, style=status_style)
            
            table.add_row(
                pod.name,
                pod.ready,
                status_text,
                str(pod.restarts),
                pod.ip,
                pod.node[:15] if pod.node else "<none>",  # Truncate node name
                pod.age,
                key=pod.name
            )
        
        # Restore cursor to target position
        if table.row_count > 0 and target_row is not None:
            row = min(target_row, table.row_count - 1)
            table.move_cursor(row=row)
            if self._restore_cursor is not None and table.row_count > self._restore_cursor:
                self._restore_cursor = None
    
    def _apply_filter(self) -> None:
        """Re-apply filter to current data."""
        if self.pods:
            self._update_table(self.pods)
    
    def _get_status_style(self, status: str) -> Style:
        """Get style for status."""
        status_colors = {
            "Running": "green",
            "Succeeded": "green",
            "Completed": "green",
            "Pending": "yellow",
            "ContainerCreating": "yellow",
            "PodInitializing": "yellow",
            "Failed": "red",
            "Error": "red",
            "CrashLoopBackOff": "red",
            "ImagePullBackOff": "red",
            "OOMKilled": "red",
            "Terminating": "magenta",
        }
        color = status_colors.get(status, "white")
        return Style(color=color)
    
    def _refresh_ages(self) -> None:
        """Refresh age column from cached pod data (no API calls)."""
        try:
            if not self.pods:
                return
            table = self.query_one("#resource-table", DataTable)
            if table.row_count == 0:
                return  # Table not ready yet
            # Age is the last column (index 6 for 7 columns)
            columns = list(table.columns.keys())
            if len(columns) < 7:
                return
            age_column_key = columns[6]
            for pod in self.pods:
                try:
                    # Recalculate age from stored created_at timestamp
                    new_age = format_age(pod.created_at)
                    table.update_cell(pod.name, age_column_key, new_age)
                except Exception:
                    pass  # Row may not exist yet
        except Exception:
            pass  # Table not ready
    
    def action_describe(self) -> None:
        """Show describe for selected pod."""
        pod_name = self._get_selected_name()
        if pod_name:
            self.app.push_screen(DescribeScreen(
                resource_type="pod",
                resource_name=pod_name,
                namespace=self.namespace
            ))
    
    def action_logs(self) -> None:
        """Show logs for selected pod - exits TUI to native terminal."""
        if self._search_active:
            self._close_search_prompt()
            return
        if self._is_prompt_active():
            footer_input = self.query_one("#footer-input", FooterPromptInput)
            self._process_footer_input(footer_input.value)
            return
        pod_name = self._get_selected_name()
        if pod_name:
            state = self._build_pods_state()
            self.app.exit(result=("logs", "pod", pod_name, self.namespace, state, pod_name))

    def action_tail_logs(self) -> None:
        """Prompt for tail line count and stream pod logs."""
        pod_name = self._get_selected_name()
        if pod_name:
            self._show_footer_prompt(
                "Tail lines (default 50). Press Enter for default.",
                lambda count, name=pod_name: self._start_tail_logs(name, count)
            )

    def action_head_logs(self) -> None:
        """Prompt for head line count and print pod logs."""
        pod_name = self._get_selected_name()
        if pod_name:
            self._show_footer_prompt(
                "Head lines (default 50). Press Enter for default.",
                lambda count, name=pod_name: self._start_head_logs(name, count)
            )

    def _build_pods_state(self) -> dict:
        table = self.query_one("#resource-table", DataTable)
        return {
            "screen": "pods",
            "namespace": self.namespace,
            "job_name": self.job_name,
            "cursor_row": table.cursor_row or 0,
            "from_jobs": self.job_name is not None,
            "jobs_cursor_row": self.jobs_cursor_row,
            "filter_text": self.filter_text,
            "jobs_filter": self.jobs_filter,
        }

    def _start_tail_logs(self, pod_name: str, line_count: int) -> None:
        state = self._build_pods_state()
        self.app.exit(result=("logs_tail", "pod", pod_name, self.namespace, line_count, state, pod_name))

    def _start_head_logs(self, pod_name: str, line_count: int) -> None:
        state = self._build_pods_state()
        self.app.exit(result=("logs_head", "pod", pod_name, self.namespace, line_count, state, pod_name))
    
    def action_shell(self) -> None:
        """Open shell in selected pod."""
        pod_name = self._get_selected_name()
        if pod_name:
            table = self.query_one("#resource-table", DataTable)
            state = {
                "screen": "pods",
                "namespace": self.namespace,
                "job_name": self.job_name,
                "cursor_row": table.cursor_row or 0,
                "from_jobs": self.job_name is not None,
                "jobs_cursor_row": self.jobs_cursor_row,  # Jobs screen cursor for restoration
                "filter_text": self.filter_text,
                "jobs_filter": self.jobs_filter,
            }
            self.app.exit(result=("exec", pod_name, self.namespace, state))
    
    def action_delete(self) -> None:
        """Delete selected pod."""
        pod_name = self._get_selected_name()
        if pod_name:
            self.app.push_screen(ConfirmDeleteScreen(
                resource_type="pod",
                resource_name=pod_name,
                namespace=self.namespace
            ))
    
    def action_all_jobs(self) -> None:
        """Go to jobs view."""
        self.app.push_screen(JobsScreen(namespace=self.namespace))
    
    def _resize_table_columns(self) -> None:
        """Recalculate all column widths on resize."""
        try:
            table = self.query_one("#resource-table", DataTable)
            if not hasattr(self, '_base_col_widths'):
                return
            widths = self._calculate_column_widths()
            columns = list(table.columns.keys())
            for i, col_key in enumerate(columns):
                col_name = self._col_order[i]
                table.columns[col_key].width = widths[col_name]
            table.refresh()
        except Exception:
            pass
    
    def _get_selected_name(self) -> Optional[str]:
        """Get the name of the selected pod."""
        table = self.query_one("#resource-table", DataTable)
        if table.cursor_row is not None and table.row_count > 0:
            # Name is the first column
            return str(table.get_cell_at((table.cursor_row, 0)))
        return None

# TODO: This entire LogScreen class can be deleted as we are printing logs directly to terminal.
class LogScreen(Screen):
    """Screen for viewing logs - uses Static widget for natural terminal-like wrapping."""
    
    BINDINGS = [
        Binding("q", "quit", "Quit", show=True, priority=True),
        Binding("Q", "quit", "Quit", show=False, priority=True),
        Binding("escape", "go_back", "Back", show=True, priority=True),
        Binding("f", "toggle_follow", "Follow", show=True),
        Binding("F", "toggle_follow", "Follow", show=False),
        Binding("g", "scroll_home", "Top", show=True),
        Binding("G", "scroll_end", "Bottom", show=True),
        Binding("ctrl+c", "quit", "Quit", show=False, priority=True),
        Binding("ctrl+C", "quit", "Quit", show=False, priority=True),
    ]
    
    following: reactive[bool] = reactive(True)
    
    def __init__(self, resource_type: str, resource_name: str, 
                 namespace: Optional[str] = None, follow: bool = True, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.resource_type = resource_type
        self.resource_name = resource_name
        self.namespace = namespace or get_current_namespace()
        self.following = follow
        self.k8s = K8sClient(namespace=self.namespace)
        self._log_text: str = ""  # Accumulate log text
        self._log_worker = None  # Track our own worker
    
    def compose(self) -> ComposeResult:
        """Compose the screen."""
        yield Static(id="header")
        yield VerticalScroll(
            Static(id="log-content", expand=True),
            id="log-container"
        )
        yield Footer()
    
    def on_mount(self) -> None:
        """Start loading logs."""
        self._update_header()
        self._log_worker = self._load_logs()
    
    def on_resize(self, event) -> None:
        """Handle terminal resize - update header."""
        self._update_header()
    
    def _update_header(self) -> None:
        """Update the header."""
        header = self.query_one("#header", Static)
        follow_indicator = "📡 follow" if self.following else "📋 static"
        title = f"logs({self.namespace}/{self.resource_name}) [{follow_indicator}]"
        
        # Build the center content first to calculate padding
        center_content = f" {title} "
        
        # Get available width (terminal width minus corners and padding)
        try:
            total_width = self.app.size.width - 4  # Account for corners and some padding
        except Exception:
            total_width = 80  # Fallback
        
        # Calculate padding on each side
        center_len = len(center_content)
        remaining = max(0, total_width - center_len)
        left_pad = remaining // 2
        right_pad = remaining - left_pad
        
        header_text = Text()
        header_text.append("┌", style="bold cyan")
        header_text.append("─" * left_pad, style="cyan")
        header_text.append(f" {title} ", style="bold white")
        header_text.append("─" * right_pad, style="cyan")
        header_text.append("┐", style="bold cyan")
        
        header.update(header_text)
    
    def _add_log_line(self, line: str) -> None:
        """Add a log line to the view."""
        self._log_text += line + "\n"
        log_content = self.query_one("#log-content", Static)
        log_content.update(self._log_text)
        
        # Auto-scroll to bottom if following
        if self.following:
            scroll_container = self.query_one("#log-container", VerticalScroll)
            scroll_container.scroll_end(animate=False)
    
    @work(exclusive=True, thread=True)
    def _load_logs(self) -> None:
        """Load logs in background."""
        worker = get_current_worker()
        
        if self.resource_type == "job":
            # Get logs from all pods of job
            pods = self.k8s.get_pods(namespace=self.namespace, job_name=self.resource_name)
            
            for pod in pods:
                if worker.is_cancelled:
                    return
                
                self.app.call_from_thread(self._add_log_line, f"\n{'='*60}")
                self.app.call_from_thread(self._add_log_line, f"Pod: {pod.name}")
                self.app.call_from_thread(self._add_log_line, f"{'='*60}\n")
                
                if self.following:
                    for line in self.k8s.stream_logs(pod.name, namespace=self.namespace):
                        if worker.is_cancelled:
                            return
                        self.app.call_from_thread(self._add_log_line, line)
                else:
                    logs = self.k8s.get_logs(pod.name, namespace=self.namespace, tail=500)
                    if logs:
                        for line in logs.split('\n'):
                            if worker.is_cancelled:
                                return
                            self.app.call_from_thread(self._add_log_line, line)
        else:
            # Single pod logs
            if self.following:
                for line in self.k8s.stream_logs(self.resource_name, namespace=self.namespace):
                    if worker.is_cancelled:
                        return
                    self.app.call_from_thread(self._add_log_line, line)
            else:
                logs = self.k8s.get_logs(self.resource_name, namespace=self.namespace, tail=500)
                if logs:
                    for line in logs.split('\n'):
                        if worker.is_cancelled:
                            return
                        self.app.call_from_thread(self._add_log_line, line)
    
    def _cleanup(self) -> None:
        """Clean up resources before exit."""
        self.k8s.kill_active_processes()
        # Only cancel our own worker, not all workers
        if self._log_worker is not None:
            self._log_worker.cancel()
            self._log_worker = None
    
    def action_go_back(self) -> None:
        """Go back to previous screen or quit if at root."""
        self._cleanup()
        if len(self.app.screen_stack) <= 2:
            self.app.exit()
        else:
            self.app.pop_screen()
    
    def action_quit(self) -> None:
        """Quit the application."""
        self._cleanup()
        self.app.exit()
    
    def on_unmount(self) -> None:
        """Clean up when screen is unmounted."""
        self._cleanup()
    
    def action_toggle_follow(self) -> None:
        """Toggle follow mode."""
        self.following = not self.following
        self._update_header()
    
    def action_scroll_home(self) -> None:
        """Scroll to top."""
        scroll_container = self.query_one("#log-container", VerticalScroll)
        scroll_container.scroll_home()
    
    def action_scroll_end(self) -> None:
        """Scroll to bottom."""
        scroll_container = self.query_one("#log-container", VerticalScroll)
        scroll_container.scroll_end()


class DescribeScreen(Screen):
    """Screen for viewing describe output - uses Static for natural wrapping."""
    
    BINDINGS = [
        Binding("q", "quit", "Quit", show=True, priority=True),
        Binding("Q", "quit", "Quit", show=False, priority=True),
        Binding("escape", "go_back", "Back", show=True, priority=True),
        Binding("g", "scroll_home", "Top", show=True),
        Binding("G", "scroll_end", "Bottom", show=True),
        Binding("j", "scroll_down", "Down", show=False),
        Binding("J", "scroll_down", "Down", show=False),
        Binding("k", "scroll_up", "Up", show=False),
        Binding("K", "scroll_up", "Up", show=False),
        Binding("ctrl+c", "quit", "Quit", show=False, priority=True),
        Binding("ctrl+C", "quit", "Quit", show=False, priority=True),
    ]
    
    def __init__(self, resource_type: str, resource_name: str, 
                 namespace: Optional[str] = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.resource_type = resource_type
        self.resource_name = resource_name
        self.namespace = namespace or get_current_namespace()
        self.k8s = K8sClient(namespace=self.namespace)
        self._describe_worker = None  # Track our own worker
    
    def compose(self) -> ComposeResult:
        """Compose the screen."""
        yield Static(id="header")
        yield VerticalScroll(
            Static(id="describe-content", expand=True),
            id="describe-container"
        )
        yield Footer()
    
    def on_mount(self) -> None:
        """Load describe output."""
        self._update_header()
        self._describe_worker = self._load_describe()
    
    def on_resize(self, event) -> None:
        """Handle terminal resize - update header."""
        self._update_header()
    
    def _update_header(self) -> None:
        """Update the header."""
        header = self.query_one("#header", Static)
        title = f"describe {self.resource_type}({self.namespace}/{self.resource_name})"
        
        # Build the center content first to calculate padding
        center_content = f" {title} "
        
        # Get available width (terminal width minus corners and padding)
        try:
            total_width = self.app.size.width - 4  # Account for corners and some padding
        except Exception:
            total_width = 80  # Fallback
        
        # Calculate padding on each side
        center_len = len(center_content)
        remaining = max(0, total_width - center_len)
        left_pad = remaining // 2
        right_pad = remaining - left_pad
        
        header_text = Text()
        header_text.append("┌", style="bold cyan")
        header_text.append("─" * left_pad, style="cyan")
        header_text.append(f" {title} ", style="bold white")
        header_text.append("─" * right_pad, style="cyan")
        header_text.append("┐", style="bold cyan")
        
        header.update(header_text)
    
    @work(thread=True)
    def _load_describe(self) -> None:
        """Load describe output in background."""
        output = self.k8s.describe(self.resource_type, self.resource_name, namespace=self.namespace)
        
        if output:
            self.app.call_from_thread(self._set_content, output)
        else:
            self.app.call_from_thread(self._set_content, f"Failed to get describe output for {self.resource_type}/{self.resource_name}")
    
    def _set_content(self, text: str) -> None:
        """Set the describe content and scroll to bottom."""
        content = self.query_one("#describe-content", Static)
        content.update(text)
        # Scroll to bottom by default (most relevant info like Events is at the bottom)
        container = self.query_one("#describe-container", VerticalScroll)
        container.scroll_end(animate=False)
    
    def action_go_back(self) -> None:
        """Go back to previous screen or quit if at root."""
        # Only cancel our own worker, not all workers
        if self._describe_worker is not None:
            self._describe_worker.cancel()
            self._describe_worker = None
        if len(self.app.screen_stack) <= 2:
            self.app.exit()
        else:
            self.app.pop_screen()
    
    def action_quit(self) -> None:
        """Quit the application."""
        if self._describe_worker is not None:
            self._describe_worker.cancel()
            self._describe_worker = None
        self.app.exit()
    
    def action_scroll_home(self) -> None:
        """Scroll to top."""
        container = self.query_one("#describe-container", VerticalScroll)
        container.scroll_home()
    
    def action_scroll_end(self) -> None:
        """Scroll to bottom."""
        container = self.query_one("#describe-container", VerticalScroll)
        container.scroll_end()
    
    def action_scroll_down(self) -> None:
        """Scroll down."""
        container = self.query_one("#describe-container", VerticalScroll)
        container.scroll_down()
    
    def action_scroll_up(self) -> None:
        """Scroll up."""
        container = self.query_one("#describe-container", VerticalScroll)
        container.scroll_up()


class ConfirmDeleteScreen(Screen):
    """Confirmation screen for deleting resources."""
    
    BINDINGS = [
        Binding("y", "select_yes", "Yes", show=False),
        Binding("Y", "select_yes", "Yes", show=False),
        Binding("n", "select_no", "No", show=False),
        Binding("N", "select_no", "No", show=False),
        Binding("enter", "confirm_selection", "Confirm", show=False),
        Binding("left", "toggle_button", "Toggle", show=False),
        Binding("right", "toggle_button", "Toggle", show=False),
        Binding("tab", "toggle_button", "Toggle", show=False),
        Binding("escape", "cancel", "Cancel", show=True, priority=True),
        Binding("ctrl+c", "cancel", "Cancel", show=False, priority=True),
        Binding("ctrl+C", "cancel", "Cancel", show=False, priority=True),
        Binding("q", "quit", "Quit", show=False, priority=True),
        Binding("Q", "quit", "Quit", show=False, priority=True),
    ]
    
    def __init__(self, resource_type: str, resource_name: str, 
                 namespace: Optional[str] = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.resource_type = resource_type
        self.resource_name = resource_name
        self.namespace = namespace or get_current_namespace()
        self.k8s = K8sClient(namespace=self.namespace)
        self.selected_yes = True  # Default to Yes
    
    def compose(self) -> ComposeResult:
        """Compose the screen."""
        yield Container(
            Static(f"Delete {self.resource_type} '{self.resource_name}'?", id="confirm-message"),
            Static("", id="btn-container"),
            Static("←/→ or y/n to select, Enter to confirm, Esc to cancel", id="confirm-hint"),
            id="confirm-dialog"
        )
    
    def on_mount(self) -> None:
        """Update button styles on mount."""
        self._update_buttons()
    
    def _update_buttons(self) -> None:
        """Update button appearance based on selection."""
        btn = self.query_one("#btn-container", Static)
        if self.selected_yes:
            btn.update("[bold white on green] Yes [/]    [dim] No [/]")
        else:
            btn.update("[dim] Yes [/]    [bold white on red] No [/]")
    
    def action_select_yes(self) -> None:
        """Select Yes."""
        self.selected_yes = True
        self._update_buttons()
    
    def action_select_no(self) -> None:
        """Select No."""
        self.selected_yes = False
        self._update_buttons()
    
    def action_toggle_button(self) -> None:
        """Toggle between Yes and No."""
        self.selected_yes = not self.selected_yes
        self._update_buttons()
    
    def action_confirm_selection(self) -> None:
        """Confirm the current selection."""
        if self.selected_yes:
            self.k8s.delete_resource(self.resource_type, self.resource_name, namespace=self.namespace)
        self.app.pop_screen()
    
    def action_cancel(self) -> None:
        """Cancel deletion."""
        self.app.pop_screen()
    
    def action_quit(self) -> None:
        """Quit the application."""
        self.app.exit()
