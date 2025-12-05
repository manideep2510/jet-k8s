# Starting Jupyter Notebook Sessions

Jet K8s allows you to launch Jupyter notebook servers on Kubernetes with automatic port forwarding.

## Basic Jupyter Session

Start a Jupyter notebook server:

```bash
jet launch jupyter my-jupyter \
  --image my-ml-image \
  --pyenv /path/to/venv
```

This will:
1. Create a Kubernetes job running Jupyter
2. Wait for the pod to be ready
3. Set up port forwarding from your local machine
4. Display the Jupyter URL and token

## Specifying Ports

Configure the port forwarding:

```bash
jet launch jupyter my-jupyter \
  --image my-ml-image \
  --port 8888:8888
```

### Port Format

```
[host_port]:[container_jupyter_port]
```

- `8888` - Use port 8888 for both local and container and start Jupyter on port 8888
- `9999:8888` - Forward local port 9999 to container port 8888 and start Jupyter on port 8888

## Mounting Notebooks Directory

Mount your notebooks directory for persistence:

```bash
jet launch jupyter my-jupyter \
  --image my-ml-image \
  --notebooks-dir /home/user/notebooks
```

This mounts your local notebooks directory into the container, so your work is saved even after the session ends.

## With Resources

Specify compute resources for your Jupyter session:

```bash
jet launch jupyter my-jupyter \
  --image my-ml-image \
  --pyenv /path/to/venv \
  --cpu 4 \
  --memory 16Gi \
  --gpu 1 \
  --gpu-type a100
```

## With Additional Volumes

Mount additional data directories:

```bash
jet launch jupyter my-jupyter \
  --image my-ml-image \
  --notebooks-dir /home/user/notebooks \
  --volume /datasets:/mnt/datasets \
  --volume /models:/mnt/models
```

## Setting a Token

Set a custom Jupyter token for authentication:

```bash
jet launch jupyter my-jupyter \
  --image my-ml-image \
  --token my-secret-token
```

If not provided, Jupyter will generate a random token which will be displayed in the logs.

## Environment Variables

Set environment variables for your Jupyter session:

```bash
jet launch jupyter my-jupyter \
  --image my-ml-image \
  --env WANDB_API_KEY=your-key \
  --env HF_TOKEN=your-token
```

## Complete Example

A full Jupyter session with all common options:

```bash
jet launch jupyter my-ml-notebook \
  --image my-ml-image:latest \
  --image-pull-policy IfNotPresent \
  --namespace ml-notebooks \
  --pyenv /home/user/envs/ml-env \
  --port 8888:8888 \
  --notebooks-dir /home/user/notebooks \
  --volume /datasets:/mnt/datasets \
  --volume /models:/mnt/models \
  --shm-size 8Gi \
  --mount-home \
  --env WANDB_PROJECT=experiments \
  --cpu 8 \
  --memory 32Gi \
  --gpu 1 \
  --gpu-type a100 \
  --token my-secret-token \
  --follow \
  --verbose
```

## Accessing Jupyter

After launching, Jet will display:
1. The pod status as it starts
2. The port forwarding information
3. The Jupyter URL (typically `http://localhost:8888`)
4. The authentication token (if not provided via `--token`)

Open the URL in your browser to access Jupyter.

## Stopping Jupyter

Press `Ctrl+C` to stop the Jupyter session. This will:
1. Stop port forwarding
2. Delete the Jupyter job and pod
3. Clean up resources

**Note**: Make sure to save your work before stopping, as the pod will be deleted.

## Saving as Template

Save your Jupyter configuration as a reusable template:

```bash
jet launch jupyter my-jupyter-template \
  --image my-ml-image \
  --pyenv /path/to/venv \
  --cpu 4 \
  --memory 16Gi \
  --gpu 1 \
  --save-template
```

Then reuse it:

```bash
jet launch jupyter my-session --template my-jupyter-template
```

## Dry Run

Preview the job YAML without launching:

```bash
jet launch jupyter my-jupyter \
  --image my-ml-image \
  --dry-run
```

## Also See

- [Submitting Jobs](https://github.com/manideep2510/jet-k8s/blob/main/docs/submitting-jobs.md) - Run batch jobs
- [Starting Debug Sessions](https://github.com/manideep2510/jet-k8s/blob/main/docs/debug-sessions.md) - Interactive shell sessions
- [Using Job Templates](https://github.com/manideep2510/jet-k8s/blob/main/docs/templates.md) - Save and reuse configuration templates
- [Monitoring Jobs](https://github.com/manideep2510/jet-k8s/blob/main/docs/monitoring-jobs.md) - TUI and real-time job monitoring