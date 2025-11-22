import logging
import subprocess
import yaml
# from kubernetes import client, config
import time
import kr8s
from kr8s.objects import Job, Pod
import os, sys
import json
import httpx
from datetime import datetime, timezone


def submit_job(job_config, dry_run=False, verbose=False):

    job_yaml = yaml.dump(job_config, sort_keys=False, default_flow_style=False)

    if dry_run:
        print("=" * 80)
        print("Dry run: Not submitting job.\nJob spec would be:")
        print("=" * 80)
        print(job_yaml)
        print("=" * 80 + "\n")
        return
    elif verbose:
        print("=" * 80)
        print("Verbose mode: Submitting job with spec:")
        print("=" * 80)
        print(job_yaml)
        print("=" * 80 + "\n")
    else:
        pass

    # TODO: Check if there is no existing job with the same name and all its pods are terminated

    # Submit the job
    try:
        result = subprocess.run(
            ['kubectl', 'apply', '-f', '-'],
            input=job_yaml,
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            if "created" in result.stdout:
                print(
                    f"\nJob \x1b[1;32m{job_config['metadata']['name']}\x1b[0m created in namespace \x1b[38;5;245m{job_config['metadata'].get('namespace', 'default')}\x1b[0m\n"
                )
            elif "configured" in result.stdout:
                print(result.stdout)
            else:
                print(result.stdout)
            # TODO: Handle immutable fields error (gracefully ask user to delete and recreate job). Add a custom exception class for this.
        else:
            raise Exception(result.stderr)
        
        # # Create job using kr8s
        # job = Job(resource=job_config, namespace=job_config['metadata'].get('namespace', 'default'))
        # job.create()
        
        # print(
        #     f"\nJob \x1b[1;32m{job_config['metadata']['name']}\x1b[0m created in namespace \x1b[38;5;245m{job_config['metadata'].get('namespace', 'default')}\x1b[0m\n"
        # )

    except Exception as e:
        print(f"Error submitting job with subprocess: {e}")


def delete_resource(name, resource_type, namespace='default'):
    """
    Delete a Kubernetes job using kubectl.

    Args:
        name (str): Name of the resource.
        resource_type (str): Type of the resource (e.g., 'job', 'pod').
        namespace (str): Kubernetes namespace.
    """
    namespace = namespace if namespace else 'default'

    try:
        logging.info(f"Deleting {resource_type} {name} in namespace {namespace}...")
        subprocess.run(
            ['kubectl', 'delete', resource_type, name, '-n', namespace],
            check=True,
            capture_output=True,
            text=True
        )

        print(f"{resource_type} \x1b[1;32m{name}\x1b[0m \x1b[31mdeleted\x1b[0m from \x1b[38;5;245m{namespace}\x1b[0m namespace")

    except subprocess.CalledProcessError as e:
        print(f"Error deleting {resource_type} {name}: {e}")

def forward_port_background(name, resource_type, host_port, pod_port, namespace='default'):
    """
    Port forward a local port to a pod port using kubectl.

    Args:
        pod_name (str): Name of the pod.
        namespace (str): Kubernetes namespace.
        local_port (int): Local port number.
        pod_port (int): Pod port number.
    """
    namespace = namespace if namespace else 'default'

    try:
        logging.info(f"Port forwarding local port {host_port} to {resource_type}/{name} port {pod_port} in namespace {namespace}...")
        proc = subprocess.Popen(
            ['kubectl', 'port-forward', f'{resource_type}/{name}', f'{host_port}:{pod_port}', '-n', namespace],
            # stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True
        )

        # Wait for the port-forwarding to start
        time.sleep(1)

        if proc.poll() is not None:
            # Process died immediately
            _, stderr = proc.communicate()
            raise Exception(f"Port forwarding failed: {stderr.strip()}")

        logging.info(
            f"Port forwarding started successfully from local port {host_port} to {resource_type}/{name} port {pod_port} in namespace {namespace} (PID: {proc.pid})")
        return proc

    except FileNotFoundError:
        raise Exception("kubectl command not found. Please install kubectl.")


def init_pod_object(resource, namespace=None, **kwargs):
    """
    Initialize a Pod object using kr8s.

    Args:
        resource (str): Name of the pod.
        namespace (str): Kubernetes namespace.
    Returns:
        Pod: kr8s Pod object.
    """

    try:
        pod = Pod(resource=resource, namespace=namespace, **kwargs)
        return pod
    except Exception as e:
        raise Exception(f"Error initializing Pod object for {resource} in namespace {namespace}: {e}")

def get_logs(pod_name, namespace, follow=True, timeout=None):
    """
    Follow logs of a pod using kr8s.

    Args:
        pod_name (str): Name of the pod.
        namespace (str): Kubernetes namespace.
        follow (bool): Whether to follow the logs.
        timeout (int): Timeout in seconds for log streaming.
    """
    namespace = namespace if namespace else 'default'

    # Initialize pod object using kr8s
    pod = init_pod_object(pod_name, namespace)

    since_time = None

    while True:
        try:
            # Refresh pod object
            pod.refresh()

            # Check if pod exists
            if not pod.exists():
                logging.warning(f"Pod {pod_name} no longer exists. Stopping log stream.")
                break

            # Check pod phase
            pod_phase = pod.status.get('phase', 'Unknown')
            # If pod is in Succeeded or Failed phase, do not follow logs
            if pod_phase in ['Succeeded', 'Failed']:
                follow = False
                logging.info(f"Pod {pod_name} is in {pod_phase} phase. Printing final logs.")
            
            for line in pod.logs(follow=follow, timeout=timeout, since_time=since_time, timestamps=False):
                print(line)
                # Update since_time to current time for next iteration
                since_time = datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + 'Z'

            # Break the loop if logs ended without exception
            break 

        # Break the loop if timeout is reached
        except (httpx.ReadTimeout, kr8s._exceptions.APITimeoutError, TimeoutError):
            logging.warning(f"Log stream timed out after {timeout} seconds. Stopping log stream.")
            break

        except httpx.RemoteProtocolError as e:
            logging.warning(f"Log stream interrupted due to protocol error: {e}. Restarting log stream in 5 seconds...")
            time.sleep(5)

        except KeyboardInterrupt:
            print("\nKeyboard interrupt received. Stopping log stream. But the job/pod will continue to run.")
            break

def get_job_pod_names(job_name, namespace='default', field_selector=None):
    """
    Get all active pod names associated with a Job (excluding terminating pods).
    
    Args:
        job_name (str): Name of the Job
        namespace (str): Kubernetes namespace
        field_selector (str): Additional field selector
    
    Returns:
        list: List of active pod names, sorted by creation time (newest first)
    """
    namespace = namespace if namespace else 'default'

    try:
        # Get pods as JSON to filter out terminating ones
        cmd = [
            'kubectl', 'get', 'pods',
            f'--namespace={namespace}',
            f'--selector=job-name={job_name}',
            '-o', 'json'
        ]
        
        if field_selector:
            cmd.insert(-2, f'--field-selector={field_selector}')

        result = subprocess.run(
            cmd, capture_output=True, text=True, check=True)
        
        pods_data = json.loads(result.stdout)
        items = pods_data.get('items', [])
        
        if not items:
            return []
        
        # Filter out pods that are being deleted (have deletionTimestamp)
        active_pods = [
            pod for pod in items
            if not pod['metadata'].get('deletionTimestamp')
        ]
        
        if not active_pods:
            return []
        
        # Sort by creation time (newest first)
        active_pods.sort(
            key=lambda p: p['metadata']['creationTimestamp'],
            reverse=True
        )
        
        # Return pod names
        return [pod['metadata']['name'] for pod in active_pods]

    except subprocess.CalledProcessError as e:
        logging.error(f"Error getting pods for job {job_name}: {e}")
        return []
    except (json.JSONDecodeError, KeyError) as e:
        logging.error(f"Error parsing pod data for job {job_name}: {e}")
        return []

def wait_for_job_pods_ready(job_name, namespace='default', timeout=300):
    """
    Wait for Job to have active pods, then wait for those pods to be ready.
    Note: This function only waits for the first active pod.

    Args:
        job_name (str): Name of the job.
        namespace (str): Kubernetes namespace.
        timeout (int): Maximum time to wait in seconds.
    """

    namespace = namespace if namespace else 'default'

    try:
        # List all pods for the job
        # Get number of active pods for the job to check if it's running
        result = subprocess.run(
            ['kubectl', 'wait', f'job/{job_name}',
             '--for=jsonpath={.status.active}',
             '--timeout=60s',
             '-n', namespace],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            # Job is running with active pods
            logging.info(f"Job {job_name} has active pods. Waiting for pods to be Ready...")

            # List active pods
            time.sleep(1)  # Small delay to ensure pods are listed

            # Get pod names that are not Succeeded or Failed or Unknown
            pod_names = get_job_pod_names(job_name, namespace, field_selector='status.phase!=Succeeded,status.phase!=Failed,status.phase!=Unknown')
            if not pod_names:
                raise Exception("No pods found for the job in running or pending state.")
            for pod_name in pod_names:
                # TODO: Print pod names if they are failed and moved on to next pod
                wait_for_pod_ready(pod_name, namespace, timeout)
                return pod_name  # Return the first pod name that is ready
        else:
            raise Exception(result.stderr)
        
    except Exception as e:
        print(f"Error getting job state: {e}")
        return None
        

def wait_for_pod_ready(pod_name, namespace='default', timeout=300):
    """
    Wait for a Kubernetes pod to be in the 'Running' state.

    Args:
        pod_name (str): Name of the pod.
        namespace (str): Kubernetes namespace.
    """

    namespace = namespace if namespace else 'default'

    try:
        # pod = Pod(resource=pod_name, namespace=namespace)
        # logging.info(
        #     f"Waiting for pod {pod_name} in namespace {pod.namespace} to be Ready...")
        # pod.wait(conditions=["condition=Ready"], timeout=timeout)
        # return

        while True:
            result = subprocess.run(
                ['kubectl', 'wait', f'pod/{pod_name}',
                '--for=condition=Ready',
                f'--timeout={timeout}s',
                '-n', namespace],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                logging.info(f"Pod {pod_name} is Ready.")
                # Check if the pod is actually running
                state_result = subprocess.run(
                    ['kubectl', 'get', 'pod', pod_name,
                    '-n', namespace,
                    '-o', 'jsonpath={.status.phase}'],
                    capture_output=True,
                    text=True
                )
                if state_result.returncode == 0:
                    pod_state = state_result.stdout.strip()
                    if pod_state == 'Running':
                        logging.info(f"Pod {pod_name} is in Running state.")
                        return
                    else:
                        logging.info(f"Pod {pod_name} is in {pod_state} state. Waiting 5 seconds...")
                        # Break to recheck the pod state
                        break
                else:
                    raise Exception(state_result.stderr)
                return
            else:
                raise Exception(result.stderr)
            
            
        
    except Exception as e:
        print(f"Error getting pod state: {e}")
        return None

def exec_into_pod(pod_name, namespace='default', shell='/bin/sh'):
    """
    Exec into a Kubernetes pod using kubectl.

    Args:
        pod_name (str): Name of the pod.
        namespace (str): Kubernetes namespace.
        shell (str): Shell to use inside the pod.
    """

    namespace = namespace if namespace else 'default'

    try:
        logging.info(f"Executing into pod {pod_name} in namespace {namespace} with shell {shell}...")
        result = subprocess.run(
            ['kubectl', 'exec', '-it', pod_name, '-n', namespace, '--', shell],
            check=False
        )

        # Exit code 130 = user pressed Ctrl+C in the shell (normal). Exit normally.
        if result.returncode == 130:
            return  
        if result.returncode == 137:
            raise Exception(f"Pod {pod_name} is terminated (exit code 137). Cannot exec into it.")
        elif result.returncode != 0:
            raise Exception(f"Error executing into pod {pod_name} with exit code {result.returncode}. stderr: {result.stderr}")
        
    except Exception as e:
        # print(f"Error executing into pod {pod_name}: {e}")
        raise Exception(e)
