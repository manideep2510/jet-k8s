# Other Commands

This document covers additional Jet commands for managing your jobs.

> **Note**: Commands like `jet logs`, `jet describe`, and `jet delete` are wrappers around `kubectl` commands that work directly on jobs by name (default). You can also specify a resource type explicitly (e.g., `jet logs pod my-pod`). `jet connect` handles job-to-pod resolution to exec into the right pod. All commands pass through additional arguments directly to kubectl, so you can use any kubectl option.

## jet logs

View and stream logs from your jobs.

Jet calls `kubectl logs` on the job directly, passing through any additional arguments you provide.

### Basic Usage

```bash
# Defaults to job resource type
jet logs my-job

# Explicitly specify resource type
jet logs pod my-pod-name
jet logs deployment my-deployment
```

### Following Logs

Stream logs in real-time (like `tail -f`):

```bash
jet logs my-job -f
```

Or:

```bash
jet logs my-job --follow
```

### Tail Last N Lines

Show only the last N lines:

```bash
jet logs my-job --tail 100
```

### Show Timestamps

Include timestamps in log output:

```bash
jet logs my-job --timestamps
```

### Logs Since Time

Show logs from a specific time:

```bash
# Last hour
jet logs my-job --since 1h

# Last 30 minutes
jet logs my-job --since 30m

# Since a specific timestamp
jet logs my-job --since-time "2024-01-15T10:00:00Z"
```

### Container-Specific Logs

For jobs with multiple containers:

```bash
jet logs my-job -c container-name
```

### Previous Container Logs

View logs from the previous container instance (useful for crash debugging):

```bash
jet logs my-job --previous
```

### Kubectl Passthrough

All arguments after the job name are passed directly to `kubectl logs`. This means any kubectl logs option works:

```bash
# These are equivalent:
jet logs my-job --tail 100 --timestamps
kubectl logs job/my-job --tail 100 --timestamps
```

Run `jet logs -h` to see all available kubectl options.

## jet describe

Get detailed information about a job.

Jet calls `kubectl describe` on the job directly, passing through any additional arguments.

### Basic Usage

```bash
# Defaults to job resource type
jet describe my-job

# Explicitly specify resource type
jet describe pod my-pod-name
jet describe deployment my-deployment
```

### Output Shows

- **Metadata**: Name, namespace, labels, annotations
- **Spec**: Container configuration, resources, volumes
- **Status**: Current state, conditions, pod IPs
- **Events**: Recent events (scheduling, image pulls, container starts)

### Output Formats

```bash
# Default human-readable format
jet describe my-job

# YAML output
jet describe my-job -o yaml

# JSON output
jet describe my-job -o json
```

### Kubectl Passthrough

All arguments after the job name are passed directly to `kubectl describe`:

```bash
# These are equivalent:
jet describe my-job -o yaml
kubectl describe job/my-job -o yaml
```

Run `jet describe -h` for all available kubectl options.

## jet connect

Connect to a running job's container with an interactive shell.

Jet finds the pod for your job and opens an interactive shell session.

### Basic Usage

```bash
jet connect my-job
```

This opens a shell session in the job's container.

You can also specify the resource type explicitly:

```bash
jet connect pod my-pod-name
jet connect job my-job-name
```

### Shell Selection

Jet automatically selects a shell in the following order:

1. The shell specified when creating the container (via `--shell`)
2. `/bin/bash` (if available in the image)
3. `/usr/bin/zsh` (if available)
4. `/usr/bin/fish` (if available)
5. `/bin/sh` (fallback)

or you can specify a shell explicitly:

```bash
jet connect my-job --shell zsh
jet connect my-job -s zsh
```

Run `jet connect -h` for all available kubectl options.


## jet delete

Delete jobs from the cluster.

### Delete Single Job

```bash
jet delete my-job
```

### Delete Multiple Jobs

```bash
jet delete job1 job2 job3
```

### Delete with Confirmation

By default, delete asks for confirmation. Skip with `--force`:

```bash
jet delete my-job --force
```

Or using the short flag:

```bash
jet delete my-job -f
```

### Delete by Pattern

Delete jobs matching a pattern:

```bash
# Delete all jobs with 'test' in the name
jet delete --name test

# Delete jobs matching regex
jet delete --regex "exp-[0-9]+-failed"
```

### Delete by Status

```bash
# Delete all failed jobs
jet delete --status failed

# Delete all completed jobs
jet delete --status completed
```

### Delete by Age

```bash
# Delete jobs older than 7 days
jet delete --older-than 7d

# Delete jobs older than 24 hours
jet delete --older-than 24h
```

### Dry Run

Preview what would be deleted:

```bash
jet delete --status failed --dry-run
```

### Grace Period

Set a grace period for termination:

```bash
jet delete my-job --grace-period 30
```

### Force Immediate Deletion

Force immediate deletion (use with caution):

```bash
jet delete my-job --force --grace-period 0
```

## jet resources
Show available cluster resources (CPU, memory, GPU). This command fetches resource metrics from `kube-state-metrics`, which is necessary to have installed in your cluster for this command to work.

```bash
jet resources

# Short alias
jet res

# Even shorter alias
jet r
```

Example Output:

```
+--------------------------------------------------------------------------------------+
|                      Cluster Resource Availability (free/total)                      |
+--------+-------------+---------------+--------+----------------------------+---------+
| Node   | CPUs        | RAM (GB)      | GPUs   | GPU Type                   | Sched   |
+========+=============+===============+========+============================+=========+
| node1  | 22.6/32.0   | 122.6/124.8   | 0/0    | N/A                        | No      |
+--------+-------------+---------------+--------+----------------------------+---------+
| node2  | 15.3/64.0   | 21.4/254.3    | 4/8    | NVIDIA RTX A6000           | Yes     |
+--------+-------------+---------------+--------+----------------------------+---------+
| node3  | 378.3/384.0 | 2258.0/2266.4 | 8/8    | NVIDIA H100 80GB HBM3      | Yes     |
+--------+-------------+---------------+--------+----------------------------+---------+
```

## Also See

- [Monitoring Jobs](https://github.com/manideep2510/jet-k8s/blob/main/docs/monitoring-jobs.md) - TUI and real-time job monitoring
- [Submitting Jobs](https://github.com/manideep2510/jet-k8s/blob/main/docs/submitting-jobs.md) - Job submission options
- [Starting Jupyter Sessions](https://github.com/manideep2510/jet-k8s/blob/main/docs/jupyter-notebooks.md) - Jupyter configuration
- [Starting Debug Sessions](https://github.com/manideep2510/jet-k8s/blob/main/docs/debug-sessions.md) - Debug session options
