# Jet: A CLI Job Execution Toolkit (Jet) for Kubernetes

Skip the YAML. A lightweight command-line Job Execution Toolkit (Jet) for Kubernetes that simplifies batch job management with a focus on ML workloads.

[![PyPI version](https://badge.fury.io/py/jet-k8s.svg)](https://badge.fury.io/py/jet-k8s) [![License: Apache-2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

## Features

- 🚀 **Simplified Job Submission** - Define and submit Kubernetes jobs directly from the command line without writing YAML files manually.
- 📊 **Easy Monitoring** - Track and manage batch jobs with a fast and responsive Terminal User Interface (TUI).
- 📄 **Work with Templates** - Save custom job templates to standardize and simplify job configurations, making your experiments reproducible.
- 📓 **Jupyter Integration** - Launch Jupyter notebooks on Kubernetes with automatic port forwarding.
- 🐛 **Debug Sessions** - Spin up interactive debug pods for quick troubleshooting.
- 🤖 **ML Focused** - Designed with Python machine learning workloads and data processing tasks in mind.

## Overview

Jet eliminates the complexity of Kubernetes YAML configuration files, providing a streamlined CLI experience for:
- Defining and submitting batch jobs
- Monitoring job status and logs with a lightweight and fast Terminal User Interface (TUI) inspired by [`k9s`](https://k9scli.io/).
- Running interactive Jupyter notebook sessions on Kubernetes with automatic port forwarding.
- Creating interactive shell debug environments for troubleshooting and debugging.
- Automatic job cleanup for Jupyter and debug sessions.

Perfect for ML engineers and researchers who want to leverage Kubernetes for ML training, inference and experimentation jobs without the YAML overhead.

## Demos 

> Click the GIFs to view the demos on Asciinema player with media controls.

### Submitting Jobs
[![til](https://github.com/manideep2510/jet-k8s/raw/main/assets/job-launch.gif)](https://asciinema.org/a/WxvEBtyK4D02BvaLI9CC5a4G4)

### Monitoring Jobs with TUI
[![tui](https://github.com/manideep2510/jet-k8s/raw/main/assets/tui.gif)](https://asciinema.org/a/b1OGpHXfY2RZXieT1EnbVPBgu)

### Starting Jupyter Notebook Sessions and Auto Port-forwarding
[![jupyter](https://github.com/manideep2510/jet-k8s/raw/main/assets/jupyter-launch.gif)](https://asciinema.org/a/y5BqZj8wB79aQTBUnHibyeAY7)

### Starting Interactive Debug Sessions
[![debug](https://github.com/manideep2510/jet-k8s/raw/main/assets/debug-launch.gif)](https://asciinema.org/a/O3V6kAflQpTaczlKsO7kVAGK2)

### Saving and Using Job Templates
[![templates](https://github.com/manideep2510/jet-k8s/raw/main/assets/job-templates.gif)](https://asciinema.org/a/ECWaEYWkT2fJfQHy4zXkow1tP)

## Installation

### Dependencies

1. Python 3.8 or higher.

2. `kubectl` installed and configured on your local machine. Refer to the [official Kubernetes documentation](https://kubernetes.io/docs/tasks/tools/) for installation instructions.

3. A running Kubernetes cluster, with kubeconfig properly set up to access the cluster from your local machine.
 
### Install Jet
Jet can be installed using pip from PyPI:

```bash
pip install jet-k8s
```

## Usage
After installation, you can use the `jet` command in your terminal. Here are some basic commands:

Please refer to the following sections for detailed user guides.

- [Submitting Jobs](https://github.com/manideep2510/jet-k8s/blob/main/docs/submitting-jobs.md)
- [Starting Jupyter Notebook Sessions](https://github.com/manideep2510/jet-k8s/blob/main/docs/jupyter-notebooks.md)
- [Starting Debug Sessions](https://github.com/manideep2510/jet-k8s/blob/main/docs/debug-sessions.md)
- [Using Job Templates](https://github.com/manideep2510/jet-k8s/blob/main/docs/templates.md)
- [Monitoring Jobs](https://github.com/manideep2510/jet-k8s/blob/main/docs/monitoring-jobs.md)
- [Other Commands](https://github.com/manideep2510/jet-k8s/blob/main/docs/other-commands.md)

## Why Jobs?

Some key reasons for using Kubernetes Jobs for ML workloads:

1. **Batch Workloads**: Jobs are designed for batch processing tasks, which aligns well with ML training and data processing workloads that are typically non-interactive and run to completion.
2. **Automatic Retry**: Jobs have built-in retry mechanisms for failed tasks, which is beneficial for long-running ML jobs that may encounter transient failures.
3. **Resource Management**: Jobs can be scheduled and managed more effectively with schedulers such as KAI-scheduler. For example, pods within jobs can be prempted and automatically rescheduled on different nodes if a high priority job needs resources or to organize pods to optimize cluster resource utilization.
4. **Completion Tracking**: Jobs provide a clear way to track the completion status of tasks, making it easier to manage and monitor ML workloads.

## Notes

1. Jet currently supports some of the frequently used job and pod spec configurations through command-line arguments. If you have specific requirements not currently supported, please raise an issue or contribute a PR to add the necessary features.

2. Jet currently supports only Kubernetes clusters with NVIDIA GPU nodes.

3. Jet currently supports only KAI-scheduler for job scheduling.
   
4. Pod's `restartPolicy` is set to `Never` for all jobs types by default and job's themselves have `backoffLimit` set to None (so defaults to Kubernetes defaults of 6). This configuration is to ensure that when the containers in pods fail, they are not restarted indefinitely on the same resources, but instead rescheduled on different resources by the job controller. You can override this using the `--restart-policy` argument.

5. The argument `--gpu-type` is implemented using node selectors. Ensure that your cluster nodes are labeled appropriately for the GPU types you intend to use.
For example, to label a node with an A100 GPU, you can use:
   ```bash
   kubectl label nodes <node-name> gpu-type=a100
   ```

6. The pod security context is set to run containers with the same user and group ID as the user executing the `jet` command. This is to ensure proper file permission handling when mounting host directories or volumes. If your use case requires running containers with different user/group IDs, please raise an issue or contribute a PR to make this configurable.

7. The `--pyenv` argument mounts a Python virtual environment from the host into the container at the same path and adjusts the containers' `PATH` environment variable accordingly. Ensure that the virtual environment is compatible with the container's image.

## TODOs:

- [ ] Add support for fractional GPUs using HAMi plugin for KAI-scheduler (In dev: [KAI-scheduler #60](https://github.com/NVIDIA/KAI-Scheduler/pull/60)).
- [ ] Add support for other accelerator types such as AMDs and TPUs.
- [ ] Disentangle from KAI-scheduler to support other similar schedulers or default K8s scheduler.
- [ ] Evaluate support for other kubernetes schedulers such as Volcano.
- [ ] Ability to submit jobs with parallism and gang scheduling for usecases such as multi-node training jobs.
- [ ] Add support for job dependencies and chaining.
- [ ] Add TUI support for port forwarding.
- [ ] Add TUI support to change namespaces and contexts.
