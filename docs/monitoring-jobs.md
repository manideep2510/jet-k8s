# Monitoring Jobs Real-time with Jet TUI

Jet K8s provides a rich terminal user interface (TUI) to monitor and manage your jobs running on Kubernetes in real-time.

## The Jet TUI

Launch the interactive terminal user interface:

```bash
jet list 
jet list jobs
```

This will open the TUI where you can see all your jobs and their statuses in real-time.

If you want to list all pods in TUI mode, you can use:

```bash
jet list pods
```

### TUI Features

The TUI provides:

- **Real-time job list**: View all your jobs with live status updates
- **Log streaming**: View job logs in real-time
- **Quick actions**: Delete, describe, or connect to jobs with keyboard shortcuts

### TUI Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `↑`/`↓` | Navigate job list |
| `Enter` or `→` | To select the job or pod |
| `←` or `Esc` | Go back |
| `l` | View job or pod logs. Press Ctrl+C to stop following logs and return to TUI |
| `d` | To describe selected job or pod |
| `x` | Delete selected job or pod |
| `s` | Exec into selected pod |
| `/` | Filter jobs or pods by name |
| `t` | Press `t` and then a number to print tail of logs and follow |
| `h` | Press `h` and then a number to print head of logs |
| `p` | Go to pods view from jobs view |
| `j` | Go to jobs view from pods view |
| `r` | Refresh job list |
| `q` or `Ctrl+C` | Quit|
