# Starting Debug Sessions

Jet provides easy access to interactive debug sessions for troubleshooting and development directly on Kubernetes.

## Basic Debug Session

Start an interactive debug session:

```bash
jet launch debug my-debug \
  --image my-ml-image --duration 3600
```

This will:
1. Create a Kubernetes job with an interactive shell
2. Wait for the pod to be ready
3. Automatically exec into the pod
4. Delete the job when you exit or after the specified duration

Note: The `--duration` flag specifies how long (in seconds) the debug session should last before automatic cleanup. Default is 21600 seconds (6 hours).

## Specifying Shell

Choose which shell to use (must be installed in the image):

```bash
jet launch debug my-debug \
  --image my-ml-image --duration 3600 \
  --shell /bin/zsh
```

> Default is `/bin/bash`. If using zsh, you may want to mount your home directory for your zsh configuration. This will also give you shell history and other settings:

```bash
jet launch debug my-debug \
  --image my-ml-image --duration 3600 \
  --shell /bin/zsh \
  --mount-home
```

Note: Ensure the specified shell is available in the container image.

## With Python Environment

Mount a Python virtual environment:

```bash
jet launch debug my-debug \
  --image my-ml-image --duration 3600 \
  --pyenv /path/to/venv
```

## With Resources

Specify compute resources:

```bash
jet launch debug my-debug \
  --image my-ml-image --duration 3600 \
  --cpu 4 \
  --memory 16Gi \
  --gpu 1 \
  --gpu-type a100
```

## With Volumes

Mount directories for accessing data or code:

```bash
jet launch debug my-debug \
  --image my-ml-image --duration 3600 \
  --volume /home/user/code:/mnt/code \
  --volume /datasets:/mnt/datasets \
  --working-dir /mnt/code
```

## Mount Home Directory

Mount your entire home directory for full access to your files and configurations including shell histories, config files, etc.:

```bash
jet launch debug my-debug \
  --image my-ml-image --duration 3600 \
  --mount-home \
  --shell /bin/zsh
```

This is useful for:
- Using your shell configuration (`.bashrc`, `.zshrc`)
- Accessing SSH keys
- Using your editor configurations

## Environment Variables

Set environment variables for the session:

```bash
jet launch debug my-debug \
  --image my-ml-image --duration 3600 \
  --env CUDA_VISIBLE_DEVICES=0 \
  --env DEBUG=1
```

## Complete Example

A full debug session with all common options:

```bash
jet launch debug my-ml-debug \
  --image my-ml-image:latest \
  --image-pull-policy IfNotPresent \
  --namespace ml-debug \
  --shell /bin/zsh \
  --pyenv /home/user/envs/ml-env \
  --duration 3600 \
  --volume /home/user/code:/mnt/code \
  --volume /datasets:/mnt/datasets \
  --working-dir /mnt/code \
  --shm-size 8Gi \
  --mount-home \
  --env WANDB_MODE=disabled \
  --cpu 8 \
  --memory 32Gi \
  --gpu 1 \
  --gpu-type a100 \
  --verbose
```

## Exiting Debug Session

Type `exit` or press `Ctrl+D` to end the debug session. This will:
1. Exit the shell
2. Automatically delete the debug job and pod
3. Clean up resources

## Use Cases

### Debugging a Failed Job

When a job fails, launch a debug session with the same configuration to investigate:

```bash
jet launch debug investigate-failure \
  --image my-ml-image --duration 3600 \
  --pyenv /path/to/venv \
  --volume /datasets:/mnt/datasets \
  --gpu 1
```

### Testing Code Changes

Test code before submitting a full job:

```bash
jet launch debug test-code \
  --image my-ml-image --duration 3600 \
  --volume /home/user/project:/mnt/project \
  --working-dir /mnt/project \
  --gpu 1
```

### Exploring the Environment

Check what's available in a container image:

```bash
jet launch debug explore-image \
  --image my-ml-image --duration 3600
```

Then inside the session:
```bash
which python
pip list
nvidia-smi
```

## Saving as Template

Save your debug configuration as a reusable template:

```bash
jet launch debug my-debug-template \
  --image my-ml-image --duration 3600 \
  --shell /bin/zsh \
  --mount-home \
  --gpu 1 \
  --save-template
```

Then reuse it:

```bash
jet launch debug quick-debug --template my-debug-template
```

## Dry Run

Preview the job YAML without launching:

```bash
jet launch debug my-debug \
  --image my-ml-image --duration 3600 \
  --dry-run
```

## Also See

- [Submitting Jobs](https://github.com/manideep2510/jet-k8s/blob/main/docs/submitting-jobs.md) - Run batch jobs
- [Starting Jupyter Sessions](https://github.com/manideep2510/jet-k8s/blob/main/docs/jupyter-notebooks.md) - Interactive notebooks
- [Using Job Templates](https://github.com/manideep2510/jet-k8s/blob/main/docs/templates.md) - Save and reuse configuration templates
- [Monitoring Jobs](https://github.com/manideep2510/jet-k8s/blob/main/docs/monitoring-jobs.md) - TUI and real-time job monitoring