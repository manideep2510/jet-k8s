# Jet K8s: Job Execution Toolkit (Jet) for Kubernetes

Skip the YAML. A lightweight command-line Job Execution Toolkit (Jet) for Kubernetes that simplifies batch job management with a focus on ML workloads.

[![PyPI version](https://badge.fury.io/py/Jet-k8s.svg)](https://badge.fury.io/py/Jet-k8s) [![License: Apache-2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

## Features

- 🚀 **Simplified Job Submission** - Define and submit Kubernetes jobs directly from the command line without writing YAML files manually.
- 📓 **Jupyter Integration** - Launch Jupyter notebooks on Kubernetes with automatic port forwarding.
- 🐛 **Debug Sessions** - Spin up interactive debug pods for quick troubleshooting.
- 📊 **Easy Monitoring** - Track and manage batch jobs with an intuitive CLI.
- 🤖 **ML Focused** - Designed with Python machine learning workloads and data processing tasks in mind.

## Overview

Jet K8s eliminates the complexity of Kubernetes YAML configuration files, providing a streamlined CLI experience for:
- Defining and submitting batch jobs
- Running interactive Jupyter notebook sessions on Kubernetes with automatic port forwarding.
- Creating interactive shell debug environments for troubleshooting and debugging.
- TODO: Monitoring job status and logs directly from the command line.
- Automatic job cleanup for Jupyter and debug sessions.

Perfect for ML engineers and researchers who want to leverage Kubernetes for ML training and inference jobs without the YAML overhead.

## Installation

You can install Jet K8s using pip:

```bash
pip install Jet-k8s
```

## Usage
After installation, you can use the `jet` command in your terminal. Here are some basic commands:

- Submit a job:
  ```bash
  jet launch job --image my-ml-image --command "python train.py"
  ```

- Submit a job with resource specifications and volume mounts:
  ```bash
  jet launch job --image my-ml-image --command "python train.py" --cpu 4 --memory 16Gi --gpu 1 --volume /data:/mnt/data
  ```

- Submit a job with python virtual environment mounted:
  ```bash
  jet launch job --image my-ml-image --command "python train.py" --pyenv /path/to/venv
  ```

- A minimal job submission example:
  ```bash
  jet launch job \
    --name my-simple-job \
    --image my-ml-image \
    --command "python train.py" \
    --pyenv /path/to/venv \
    --volume /data1:/mnt/data1 /data2:/mnt/data2 \
    --cpu 2 \
    --memory 8Gi \
    --gpu 1 
  ```

- A complete job submission example:
  ```bash
  jet launch job \
    --name my-ml-job \
    --image my-ml-image \
    --image-pull-policy IfNotPresent \
    --shell /bin/bash \
    --command "python train.py --epochs 10" \
    --pyenv /path/to/venv \
    --restart-policy OnFailure \
    --cpu 4 \
    --memory 16Gi \
    --gpu 1 \
    --gpu-type h100 \
    --node-selector kubernetes.io/hostname=node1 \
    --volume /data1:/mnt/data1 /data2:/mnt/data2 \
    --volume /data3:/mnt/data3 \
    --shm-size 1Gi \
    --mount-home \
    --env ENV1=value1 ENV2=value2 \
    --env ENV3=value3 \
    --follow \ # Streams job and pod creation status and logs of scheduled pods
    --verbose
  ```

- Start a Jupyter notebook session:
  ```bash
  jet launch jupyter \ 
    --name my-jupyter-notebook \
    --image my-ml-image \
    --image-pull-policy IfNotPresent \
    --pyenv /path/to/venv \
    --port 8888:8888 \
    --notebooks-dir /path/to/notebooks \
    --volume /data:/mnt/data \
    --shm-size 1Gi \
    --env ENV1=value1 ENV2=value2 \
    --cpu 4 \
    --memory 16Gi \
    --gpu 1 \
    --gpu-type a6000 \
    --follow
    --verbose
  ```

- Start a debug session:
  ```bash
  jet launch debug \
    --name my-debug-session \
    --image my-ml-image \
    --image-pull-policy IfNotPresent \
    --pyenv /path/to/venv \
    --shell zsh \ # The specified shell should be pre-installed in the image
    --volume /data:/mnt/data \
    --shm-size 1Gi \
    --env ENV1=value1 ENV2=value2 \
    --mount-home \ # This will mount the user's home directory into the debug pod
    --cpu 4 \
    --memory 16Gi \
    --gpu 1 \
    --gpu-type v100 \
    --follow
    --verbose
  ```

TODO: Monitor jobs, view logs, connect to running jobs, delete jobs commands

## Notes

1. Jet K8s currenty supports only Kubernetes clusters with NVIDIA GPU nodes.

2. Jet K8S currently only supports KAI Scheduler for job scheduling.

3. The argument `--gpu-type` is implemented using node selectors. Ensure that your cluster nodes are labeled appropriately for the GPU types you intend to use.
For example, to label a node with an A100 GPU, you can use:
   ```bash
   kubectl label nodes <node-name> gpu-type=a100
   ```