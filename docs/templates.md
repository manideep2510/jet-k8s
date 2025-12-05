# Using Job Templates

Jet K8s allows you to save job configurations as templates for easy reuse and standardization.

## Saving a Template

Add `--save-template` to any job launch command to save it as a template instead of running it:

```bash
jet launch job my-ml-template \
  --image my-ml-image \
  --pyenv /path/to/venv \
  --cpu 4 \
  --memory 16Gi \
  --gpu 1 \
  --volume /datasets:/mnt/datasets \
  --save-template
```

The template is saved to `~/.local/share/jet/templates/` or `$XDG_DATA_HOME/jet/templates/` with the job name.

## Using a Template

Launch a job using a saved template:

```bash
jet launch job my-new-job --template my-ml-template
```

### Overriding Template Values

You can override any template value with command-line arguments:

```bash
# Override the command
jet launch job my-job --template my-ml-template --command "python eval.py"

# Override resources
jet launch job my-job --template my-ml-template --gpu 2 --memory 32Gi

# Override multiple values
jet launch job my-job --template my-ml-template \
  --command "python train.py --epochs 200" \
  --gpu 2 \
  --env BATCH_SIZE=64
```

The job name in the command always overrides the template's job name.

## Template Types

Templates can be created for any job type:

### Job Templates

```bash
jet launch job my-job-template \
  --image my-image \
  --command "python train.py" \
  --gpu 1 \
  --save-template
```

### Jupyter Templates

```bash
jet launch jupyter my-jupyter-template \
  --image my-image \
  --pyenv /path/to/venv \
  --cpu 4 \
  --memory 16Gi \
  --gpu 1 \
  --save-template
```

### Debug Templates

```bash
jet launch debug my-debug-template \
  --image my-image \
  --shell /bin/zsh \
  --mount-home \
  --gpu 1 \
  --save-template
```

## Listing Templates

View all saved templates:

```bash
jet list templates
```

### Filter by Type

```bash
# List only job templates
jet list templates --type job

# List only jupyter templates
jet list templates --type jupyter

# List only debug templates
jet list templates --type debug
```

### Filter by Name

```bash
# Filter by substring match
jet list templates --name ml

# Filter by regex pattern
jet list templates --regex ".*-v[0-9]+"
```

### Sort Templates

```bash
# Sort by name (default)
jet list templates --sort-by name

# Sort by creation time
jet list templates --sort-by time
```

### Verbose Output

Show detailed template information:

```bash
jet list templates --verbose
```

## Using External Template Files

You can also use a YAML file as a template:

```bash
jet launch job my-job --template /path/to/template.yaml
```

## Template Storage

Templates are stored in `~/.local/share/jet/templates/` or `$XDG_DATA_HOME/jet/templates/` as YAML files:

```
~/.local/share/jet/templates/ or $XDG_DATA_HOME/jet/templates/
├── job/
│   ├── my-job-template.yaml
│   └── training-template.yaml
├── jupyter/
│   └── my-jupyter-template.yaml
└── debug/
    └── my-debug-template.yaml
```

## Example Workflow

### 1. Create a Base Template

```bash
jet launch job base-ml-job \
  --image my-ml-image:latest \
  --pyenv /home/user/envs/ml \
  --cpu 4 \
  --memory 16Gi \
  --gpu 1 \
  --volume /datasets:/mnt/datasets \
  --shm-size 8Gi \
  --mount-home \
  --save-template
```

### 2. Use Template for Different Experiments

```bash
# Experiment 1: Training with default settings
jet launch job exp1-baseline --template base-ml-job \
  --command "python train.py --model resnet50"

# Experiment 2: Training with more resources
jet launch job exp2-large --template base-ml-job \
  --command "python train.py --model resnet101" \
  --gpu 2 \
  --memory 32Gi

# Experiment 3: Evaluation
jet launch job exp3-eval --template base-ml-job \
  --command "python eval.py --checkpoint /mnt/datasets/model.pt"
```

### 3. Create Specialized Templates

```bash
# Create a template specifically for evaluation
jet launch job eval-template --template base-ml-job \
  --command "python eval.py" \
  --gpu 1 \
  --save-template

# Use the eval template
jet launch job my-eval --template eval-template \
  --env CHECKPOINT=/mnt/datasets/best-model.pt
```

## Best Practices

1. **Use descriptive names**: Name templates clearly to indicate their purpose (e.g., `training-4gpu`, `jupyter-debug`, `eval-cpu-only`)

2. **Create base templates**: Start with a base template containing common settings, then create specialized templates from it

3. **Version templates**: Include version numbers in template names for tracking (e.g., `ml-training-v2`)

4. **Review with dry-run**: Use `--dry-run` when trying a new template to verify the configuration

```bash
jet launch job test --template my-template --dry-run
```

## Also See

- [Submitting Jobs](https://github.com/manideep2510/jet-k8s/blob/main/docs/submitting-jobs.md) - Job submission options
- [Starting Jupyter Sessions](https://github.com/manideep2510/jet-k8s/blob/main/docs/jupyter-notebooks.md) - Jupyter configuration
- [Starting Debug Sessions](https://github.com/manideep2510/jet-k8s/blob/main/docs/debug-sessions.md) - Debug session options
- [Monitoring Jobs](https://github.com/manideep2510/jet-k8s/blob/main/docs/monitoring-jobs.md) - TUI and real-time job monitoring