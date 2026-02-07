# Services

Jet can create Kubernetes ClusterIP Services to expose your pods within the cluster through a stable DNS name.

## Basic Usage

Create a service that routes traffic to pods with a specific label:

```bash
jet launch service my-svc --selector app=my-app --port 80:8000
```

This creates a ClusterIP Service that:
- Routes traffic from port `80` to port `8000` of the pods
- Selects pods with label `app=my-app`
- Is accessible within the namespace at `my-svc` or at `my-svc.<namespace>.svc.cluster.local` from other namespaces.

### List Services

```bash
kubectl get services

kubectl get svc
```

## Command Syntax

```bash
jet launch service <name> --selector <key=value> --port <service_port>:<target_port>
```

Or using the short alias:

```bash
jet launch svc <name> -s <key=value> -p <service_port>:<target_port>
```

## Options

| Option | Short | Description |
|--------|-------|-------------|
| `--selector` | `-s` | Pod selector labels (required). Format: `key=value` |
| `--port` | `-p` | Port mapping (required). Format: `<service_port>[:<target_port>]` |
| `--namespace` | `-n` | Kubernetes namespace |
| `--dry-run` | | Print YAML without submitting |
| `--verbose` | | Print YAML and submit |

## Multiple Ports

Expose multiple ports by specifying `--port` multiple times:

```bash
jet launch svc my-svc \
  -s app=my-app \
  -p 80:8000 \
  -p 443:8443 \
  -p 9090:metrics
```

### Port Auto-Naming

Ports are automatically named based on their service port number:
- Port `80` → `http`
- Port `443` → `https`
- Other ports → `port-0`, `port-1`, etc.

## Named Target Ports

Target ports can be numbers or named ports defined in your pod spec:

```bash
# Numeric target port
jet launch svc my-svc -s app=my-app -p 80:8000

# Named target port (must match containerPort name in pod spec)
jet launch svc my-svc -s app=my-app -p 80:http -p 443:https
```

## Multiple Selectors

Select pods matching multiple labels:

```bash
jet launch svc my-svc \
  -s app=my-app \
  -s tier=frontend \
  -p 80:8000
```

## Dry Run

Preview the generated YAML without creating the service:

```bash
jet launch svc my-svc -s app=my-app -p 80:8000 --dry-run
```

Output:
```yaml
apiVersion: v1
kind: Service
metadata:
  name: my-svc
  namespace: my-namespace
spec:
  selector:
    app: my-app
  ports:
  - name: http
    protocol: TCP
    port: 80
    targetPort: 8000
```

## Accessing the Service

### From Within the Same Namespace

```bash
curl http://my-svc:80
```

### From Another Namespace

```bash
curl http://my-svc.my-namespace.svc.cluster.local:80
```

### Port Forwarding (Local Development)

To access the service from your local machine:

```bash
kubectl port-forward svc/my-svc 8080:80
```

Then access at `http://localhost:8080`

## Deleting a Service

Use `kubectl` to delete the service:

```bash
kubectl delete svc my-svc
```
