# Jet K8s: Job Execution Toolkit (Jet) for Kubernetes

Skip the YAML. A lightweight command-line Job Execution Toolkit (Jet) for Kubernetes that simplifies batch job management with a focus on ML workloads.

[![PyPI version](https://badge.fury.io/py/Jet-k8s.svg)](https://badge.fury.io/py/Jet-k8s) [![License: Apache-2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

## Features

- 🚀 **Simplified Job Submission** - Define and submit Kubernetes jobs directly from the command line without writing YAML files manually.
- TODO: 📄 **Work with Templates** - Save custom job templates to standardize and simplify job configurations, making your experiments reproducible.
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
  jet launch job my-simple-job --image my-ml-image --command "python train.py"
  ```

- Submit a job with resource specifications and volume mounts:
  ```bash
  jet launch job my-resource-job --image my-ml-image --command "python train.py" --cpu 4 --memory 16Gi --gpu 1 --volume /data:/mnt/data
  ```

- Submit a job with python virtual environment mounted:
  ```bash
  jet launch job my-python-job --image my-ml-image --command "python train.py" --pyenv /path/to/venv
  ```

- A minimal job submission example:
  ```bash
  jet launch job my-simple-job \
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
  jet launch job my-ml-job \
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

- Define and save a job template:
  ```bash
  jet launch job my-ml-job-template \ # It can be jet launch template job/jupyter/debug ...
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
    --save-template # Just pass this flag to save the template. Job will not actually be launched if this flag is provided.

  # Saves the template as 'my-ml-job' in the local Jet K8s template store
  ```

- Launch a job using a saved template:
  ```bash
  # Additional arguments like --command can override the configuration defined in the template
  # Job name provided in the command will override the job name in the template
  jet launch job my-ml-job --template my-ml-job-template --command "python train.py --epochs 20"
  ```

- Start a Jupyter notebook session:
  ```bash
  jet launch jupyter my-jupyter-notebook \
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
  jet launch debug my-debug-session \
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

## Why Jobs?

I conciously chose to focus on Kubernetes Jobs rather than Pods or Deployments for the following reasons:

#### TODO: Explain why Jobs are chosen over Pods/Deployments

## Notes

1. Jet K8s currenty supports only Kubernetes clusters with NVIDIA GPU nodes.

2. Jet K8S currently only supports KAI Scheduler for job scheduling.

3. Pod's `restartPolicy` is set to `Never` for all jobs types by default and job's themselves have `backoffLimit` set to None (so defaults to Kubernetes defaults of 6). This configuration is to ensure that when the containers in pods fail, they are not restarted indefinitely on the same resources, but instead rescheduled on different resources by the job controller. You can override this using the `--restart-policy` argument.

4. The argument `--gpu-type` is implemented using node selectors. Ensure that your cluster nodes are labeled appropriately for the GPU types you intend to use.
For example, to label a node with an A100 GPU, you can use:
   ```bash
   kubectl label nodes <node-name> gpu-type=a100
   ```

5. The pod security context is set to run containers with the same user and group ID as the user executing the `jet` command. This is to ensure proper file permission handling when mounting host directories or volumes. If your use case requires running containers with different user/group IDs, please raise an issue or contribute a PR to make this configurable.

6. The --pyenv argument mounts a Python virtual environment from the host into the container at the same path and adjusts the containers' `PATH` environment variable accordingly. Ensure that the virtual environment is compatible with the container's image.