"""Main Jet TUI Application."""
from textual.app import App
from textual.binding import Binding
from typing import Optional, List

from .screens import JobsScreen, PodsScreen, DescribeScreen
from .styles import STYLES
from ..utils import get_current_namespace, detect_shell, exec_into_pod


class JetTUI(App):
    """Lightweight k8s resource browser like k9s."""
    
    TITLE = "Jet"
    CSS = STYLES
    ENABLE_COMMAND_PALETTE = False  # Disable command palette
    
    BINDINGS = [
        Binding("q", "quit", "Quit", show=True, priority=True),
        Binding("Q", "quit", "Quit", show=False, priority=True),
        Binding("ctrl+c", "quit", "Quit", show=False, priority=True),
        Binding("ctrl+C", "quit", "Quit", show=False, priority=True),
    ]
    
    def __init__(self, mode: str = "jobs", namespace: Optional[str] = None, 
                 resource_name: Optional[str] = None, follow: bool = False,
                 job_name: Optional[str] = None, resource_type: Optional[str] = None,
                 restore_state: Optional[dict] = None,
                 *args, **kwargs):
        """
        Initialize the TUI.
        
        Args:
            mode: One of "jobs", "pods", "logs", "describe"
            namespace: Kubernetes namespace (uses current context if not provided)
            resource_name: Name of specific resource (for logs/describe)
            follow: Whether to follow logs
            job_name: Filter pods by job name
            resource_type: Type of resource ("job", "pod")
            restore_state: State to restore after returning from logs/exec
        """
        super().__init__(*args, **kwargs)
        self.mode = mode
        self.namespace = namespace or get_current_namespace()
        self.resource_name = resource_name
        self.follow = follow
        self.job_name = job_name
        self.resource_type = resource_type
        self.restore_state = restore_state
    
    def action_quit(self) -> None:
        """Quit the application, canceling all workers first."""
        self._cleanup_and_exit()
    
    def _cleanup_and_exit(self) -> None:
        """Clean up all workers and timers, then exit."""
        # Stop timers and cancel workers in all screens
        for screen in self.screen_stack:
            if hasattr(screen, '_refresh_timer') and screen._refresh_timer:
                screen._refresh_timer.stop()
            if hasattr(screen, '_is_active'):
                screen._is_active = False
            if hasattr(screen, 'workers'):
                screen.workers.cancel_all()
        self.workers.cancel_all()
        self.exit()
    
    def on_mount(self) -> None:
        """Set up the initial screen based on mode."""
        if self.restore_state:
            # Restore previous state after returning from logs/exec
            state = self.restore_state
            ns = state.get("namespace") or self.namespace
            
            if state.get("screen") == "pods":
                screen = PodsScreen(
                    namespace=ns,
                    job_name=state.get("job_name"),
                    jobs_cursor_row=state.get("jobs_cursor_row"),  # Pass through for future use
                    jobs_filter=state.get("jobs_filter"),  # Restore jobs filter
                    initial_filter=state.get("filter_text"),  # Restore pods filter
                )
                screen._restore_cursor = state.get("cursor_row", 0)
                # First push jobs screen if we came from there
                if state.get("from_jobs"):
                    jobs_screen = JobsScreen(
                        namespace=ns,
                        initial_filter=state.get("jobs_filter"),  # Restore jobs filter
                    )
                    jobs_screen._restore_cursor = state.get("jobs_cursor_row")
                    self.push_screen(jobs_screen)
                self.push_screen(screen)
            elif state.get("screen") == "jobs":
                screen = JobsScreen(
                    namespace=ns,
                    initial_filter=state.get("filter_text"),  # Restore jobs filter
                )
                screen._restore_cursor = state.get("cursor_row", 0)
                self.push_screen(screen)
            else:
                self.push_screen(JobsScreen(namespace=self.namespace))
        elif self.mode == "jobs":
            self.push_screen(JobsScreen(namespace=self.namespace))
        elif self.mode == "pods":
            self.push_screen(PodsScreen(namespace=self.namespace, job_name=self.job_name))
        elif self.mode == "describe":
            if self.resource_name and self.resource_type:
                self.push_screen(DescribeScreen(
                    resource_type=self.resource_type,
                    resource_name=self.resource_name,
                    namespace=self.namespace
                ))
            else:
                self.push_screen(JobsScreen(namespace=self.namespace))
        else:
            # Default to jobs view
            self.push_screen(JobsScreen(namespace=self.namespace))


def run_tui(mode: str = "jobs", namespace: Optional[str] = None, 
            resource_name: Optional[str] = None, follow: bool = False,
            job_name: Optional[str] = None, resource_type: Optional[str] = None,
            mouse: bool = False):
    """
    Run the Jet TUI.
    
    Args:
        mode: One of "list", "logs", "describe"
        namespace: Kubernetes namespace (uses current context if not provided)
        resource_name: Name of specific resource
        follow: Whether to follow logs
        job_name: Job name for filtering pods or logs
        resource_type: Type of resource ("job", "pod")
        mouse: Whether to enable mouse input (default: False)
    
    Returns:
        Optional tuple with action to perform after exit
    """
    import os
    import subprocess
    import threading
    import time
    import shutil
    
    def get_border_line() -> str:
        """Get a border line that fits the terminal width."""
        width = shutil.get_terminal_size((80, 24)).columns
        return "\033[1;36m" + "─" * width + "\033[0m"

    def print_banner(title: str, info_lines: Optional[List[str]] = None) -> None:
        lines = info_lines or []
        border = get_border_line()
        print(border)
        print(f"\033[1;37m  {title}\033[0m")
        print(border)
        for line in lines:
            print(line)
        print(border + "\n")

    def prompt_return(message: str) -> None:
        border = get_border_line()
        print(f"\n{border}")
        print(message)
        print(border, flush=True)
        try:
            input()
        except (KeyboardInterrupt, EOFError):
            pass

    def handle_follow_logs(title: str, cmd: List[str], info_lines: Optional[List[str]], state: dict) -> dict:
        lines = list(info_lines or [])
        lines.append("\033[33m  Ctrl+C to return to TUI\033[0m")
        print_banner(title, lines)
        user_interrupted = False
        try:
            subprocess.run(cmd)
        except KeyboardInterrupt:
            user_interrupted = True
        if not user_interrupted:
            prompt_return("\033[33m  End of logs. Press Enter or Ctrl+C to return to TUI\033[0m")
        print(f"\n\033[1;32m  Returning to TUI...\033[0m")
        time.sleep(0.2)
        return state

    def stream_head_lines(cmd: List[str], line_count: int) -> None:
        """Fetch all logs and display only the first N lines chronologically."""
        try:
            # Fetch all logs at once to get them in chronological order
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=30,  # Timeout to prevent hanging on huge logs
            )
            lines = result.stdout.splitlines()
            # Print the first N lines
            for line in lines[:line_count]:
                print(line, flush=True)
        except subprocess.TimeoutExpired:
            print("\033[33m  (Log fetch timed out - showing partial output)\033[0m")
    
    # Use context namespace if not specified
    if namespace is None:
        namespace = get_current_namespace()
    
    # For direct log mode, just run kubectl logs without TUI
    if mode == "logs":
        try:
            if job_name:
                cmd = ["kubectl", "logs", "-l", f"job-name={job_name}", "-n", namespace, "--all-containers=true"]
                if follow:
                    cmd.insert(2, "-f")
            elif resource_name:
                cmd = ["kubectl", "logs", resource_name, "-n", namespace, "--all-containers=true"]
                if follow:
                    cmd.insert(2, "-f")
            else:
                print("Error: No resource specified for logs")
                return
            subprocess.run(cmd)
        except KeyboardInterrupt:
            pass
        return
    
    restore_state = None
    
    while True:
        app = JetTUI(
            mode=mode,
            namespace=namespace,
            resource_name=resource_name,
            follow=follow,
            job_name=job_name,
            resource_type=resource_type,
            restore_state=restore_state
        )
        
        result = None
        exit_event = threading.Event()
        
        def force_exit_after_timeout():
            """Force exit if normal shutdown takes too long."""
            if not exit_event.wait(timeout=0.5):
                os._exit(0)
        
        try:
            result = app.run(mouse=mouse)
        except KeyboardInterrupt:
            os._exit(0)
        finally:
            exit_thread = threading.Thread(target=force_exit_after_timeout, daemon=True)
            exit_thread.start()
        
        exit_event.set()
        
        # Handle special exit results (actions to perform)
        if result and isinstance(result, tuple):
            action = result[0]
            
            if action == "logs":
                # Run kubectl logs directly - terminal handles everything
                _, res_type, res_name, ns, state, selected_name = result
                if res_type == "job":
                    cmd = ["kubectl", "logs", "-f", "--tail=-1", f"job/{res_name}", "-n", ns, "--all-containers=true"]
                else:
                    cmd = ["kubectl", "logs", "-f", "--tail=-1", res_name, "-n", ns, "--all-containers=true"]
                title = f"Logs: {res_type}/{res_name} ({ns})"
                restore_state = handle_follow_logs(title, cmd, None, state)
                continue
            elif action == "logs_tail":
                _, res_type, res_name, ns, line_count, state, selected_name = result
                count = max(1, int(line_count))
                if res_type == "job":
                    cmd = [
                        "kubectl", "logs", "-f", f"--tail={count}",
                        f"job/{res_name}", "-n", ns, "--all-containers=true"
                    ]
                else:
                    cmd = [
                        "kubectl", "logs", "-f", f"--tail={count}",
                        res_name, "-n", ns, "--all-containers=true"
                    ]
                info_lines = [f"\033[36m  Tail: showing last {count} lines. Following output...\033[0m"]
                title = f"Logs: {res_type}/{res_name} ({ns})"
                restore_state = handle_follow_logs(title, cmd, info_lines, state)
                continue
            elif action == "logs_head":
                _, res_type, res_name, ns, line_count, state, selected_name = result
                count = max(1, int(line_count))
                if res_type == "job":
                    cmd = [
                        "kubectl", "logs",
                        f"job/{res_name}", "-n", ns, "--all-containers=true"
                    ]
                else:
                    cmd = [
                        "kubectl", "logs",
                        res_name, "-n", ns, "--all-containers=true"
                    ]
                info_lines = [
                    f"\033[36m  Head: showing first {count} lines (static preview).\033[0m",
                    "\033[33m  Output stops automatically; press Ctrl+C to cancel early.\033[0m",
                ]
                title = f"Logs: {res_type}/{res_name} ({ns})"
                print_banner(title, info_lines)
                user_interrupted = False
                try:
                    stream_head_lines(cmd, count)
                except KeyboardInterrupt:
                    user_interrupted = True
                if not user_interrupted:
                    prompt_return(
                        f"\033[33m  Displayed first {count} lines. End of logs preview. Press Enter or Ctrl+C to return to TUI\033[0m"
                    )
                print(f"\n\033[1;32m  Returning to TUI...\033[0m")
                time.sleep(0.2)
                restore_state = state
                continue
                
            elif action == "exec":
                # Run kubectl exec directly in terminal
                _, pod_name, ns, state = result
                border = get_border_line()
                print(border)
                print(f"\033[1;37m  Shell: {pod_name} ({ns})\033[0m")
                print(border)
                print(f"\033[33m  Type 'exit' to return to TUI\033[0m")
                print(border + "\n")
                # Get shell type from container spec if available, else default to /bin/sh
                shell_type = detect_shell(pod_name, ns)
                try:
                    exec_into_pod(pod_name, ns, shell=shell_type)
                except KeyboardInterrupt:
                    pass
                print(f"\n\033[1;32m  Returning to TUI...\033[0m\n")
                time.sleep(0.3)
                restore_state = state
                continue
        
        # Normal exit
        break
