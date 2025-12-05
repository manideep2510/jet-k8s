# Submitting Jobs

Jet K8s makes it easy to submit jobs to Kubernetes without writing YAML files.

## Basic Job Submission

Submit a simple job with an image and command:

```bash
jet launch job my-job --image python:3.11 --command 'python -c "print(\"hello world\")"'
```

## Job with Resources

Specify CPU, memory, and GPU resources:

```bash
jet launch job my-ml-job \
  --image my-ml-image \
  --command "python train.py" \
  --cpu 4 \
  --memory 16Gi \
  --gpu 1
```

### Resource Format

- `--cpu`: CPU request and limit. Format: `request[:limit]` (e.g., `4` or `2:4`)
- `--memory`: Memory request and limit. Format: `request[:limit]` (e.g., `8Gi` or `4Gi:8Gi`)
- `--gpu`: Number of GPUs to request
- `--gpu-type`: Type of GPU (e.g., `a100`, `h100`, `v100`)

## Job with Volumes

Mount host directories into the container:

```bash
jet launch job my-job \
  --image my-image \
  --command "python process.py" \
  --volume /mnt/data:/data \
  --volume /mnt/models:/models
```

### Volume Format

```
[<volume_name>:]<host_path>[:<mount_path>][:Type]
```

Examples:
- `/data` - Mount `/data` from host to `/data` in container
- `/mnt/data:/data` - Mount `/mnt/data` from host to `/data` in container
- `my-vol:/mnt/data:/data` - Named volume mount

## Job with Python Environment

Mount a Python virtual environment (venv, conda, or uv):

```bash
jet launch job my-job \
  --image my-image \
  --command "python train.py" \
  --pyenv /path/to/venv
```

This automatically:
- Mounts the virtual environment into the container
- Adds the environment's bin directory to PATH

## Job with Environment Variables

Set environment variables:

```bash
jet launch job my-job \
  --image my-image \
  --command "python train.py" \
  --env BATCH_SIZE=32 LEARNING_RATE=0.001 \
  --env WANDB_API_KEY=your-key
```

You can also pass an env file:

```bash
jet launch job my-job \
  --image my-image \
  --command "python train.py" \
  --env .env
```

## Advanced Options

### Shell Selection

Specify which shell to use for the command:

```bash
jet launch job my-job \
  --image my-image \
  --shell /bin/bash \
  --command "source setup.sh && python train.py"
```

### Image Pull Policy

Control when images are pulled:

```bash
jet launch job my-job \
  --image my-image \
  --image-pull-policy Always \
  --command "python train.py"
```

Options: `IfNotPresent`, `Always`, `Never`

### Restart Policy

Set the pod restart policy:

```bash
jet launch job my-job \
  --image my-image \
  --restart-policy OnFailure \
  --command "python train.py"
```

Options: `Never` (default), `OnFailure`, `Always`

### Shared Memory Size

Increase shared memory for data loaders:

```bash
jet launch job my-job \
  --image my-image \
  --command "python train.py" \
  --shm-size 8Gi
```

### Mount Home Directory

Mount your home directory into the container:

```bash
jet launch job my-job \
  --image my-image \
  --command "python train.py" \
  --mount-home
```

### Node Selection

Select specific nodes using node selectors:

```bash
jet launch job my-job \
  --image my-image \
  --command "python train.py" \
  --node-selector kubernetes.io/hostname=node1
```

### Working Directory

Set the working directory inside the container:

```bash
jet launch job my-job \
  --image my-image \
  --command "python train.py" \
  --working-dir /app
```

## Following Job Logs (Yet to be implemented)

Use `--follow` to stream job status and logs:

```bash
jet launch job my-job \
  --image my-image \
  --command "python train.py" \
  --follow
```

## Dry Run

Preview the job YAML without submitting:

```bash
jet launch job my-job \
  --image my-image \
  --command "python train.py" \
  --dry-run
```

## Verbose Output

Show detailed YAML and debug info:

```bash
jet launch job my-job \
  --image my-image \
  --command "python train.py" \
  --verbose
```

## Complete Example

A full job submission with all common options:

```bash
jet launch job my-ml-training \
  --image my-ml-image:latest \
  --image-pull-policy IfNotPresent \
  --namespace ml-jobs \
  --shell /bin/bash \
  --command "python train.py --epochs 100" \
  --pyenv /home/user/envs/ml-env \
  --restart-policy OnFailure \
  --cpu 8 \
  --memory 32Gi \
  --gpu 2 \
  --gpu-type a100 \
  --node-selector gpu-type=a100 \
  --volume /datasets:/mnt/datasets \
  --volume /checkpoints:/mnt/checkpoints \
  --shm-size 16Gi \
  --mount-home \
  --env WANDB_PROJECT=my-project \
  --env CUDA_VISIBLE_DEVICES=0,1 \
  --working-dir /app \
  --follow \
  --verbose
```

## Also See

- [Starting Jupyter Sessions](https://github.com/manideep2510/jet-k8s/blob/main/docs/jupyter-notebooks.md) - Jupyter configuration
- [Starting Debug Sessions](https://github.com/manideep2510/jet-k8s/blob/main/docs/debug-sessions.md) - Debug session options
- [Using Job Templates](https://github.com/manideep2510/jet-k8s/blob/main/docs/templates.md) - Save and reuse job configuration templates
- [Monitoring Jobs](https://github.com/manideep2510/jet-k8s/blob/main/docs/monitoring-jobs.md) - TUI and real-time job monitoring
- [Other Commands](https://github.com/manideep2510/jet-k8s/blob/main/docs/other-commands.md) - Delete, describe, and manage jobs