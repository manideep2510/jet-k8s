import logging
import subprocess
import yaml
import time
import os
import kr8s
from kr8s.objects import Job, Pod
import json
import httpx
from datetime import datetime, timezone
from pathlib import Path
import re
from collections import defaultdict
import shutil
import textwrap
from .defaults import JET_HOME
from .k8s_events import K8S_EVENTS


def get_kubeconfig():
    """
    Get the merged kubeconfig following kubectl's precedence rules.
    
    Resolution order (matches kubectl exactly):
    1. $KUBECONFIG environment variable (colon-separated list of files, merged in order)
    2. ~/.kube/config
    
    Returns:
        dict: Merged kubeconfig dictionary, or empty dict if no config found.
    """
    kubeconfig_env = os.environ.get("KUBECONFIG", "")
    
    if kubeconfig_env:
        # KUBECONFIG can be colon-separated list of files (or semicolon on Windows)
        separator = ";" if os.name == "nt" else ":"
        config_paths = [Path(p.strip()).expanduser() for p in kubeconfig_env.split(separator) if p.strip()]
    else:
        # Default: ~/.kube/config
        config_paths = [Path.home() / ".kube" / "config"]
    
    # Merge configs in order (later files override earlier for conflicts,
    # but kubectl merges lists like contexts/clusters/users)
    merged = {
        "clusters": [],
        "contexts": [],
        "users": [],
        "current-context": None,
    }
    
    seen_clusters = set()
    seen_contexts = set()
    seen_users = set()
    
    for config_path in config_paths:
        if not config_path.exists():
            continue
        try:
            with open(config_path) as f:
                cfg = yaml.safe_load(f) or {}
            
            # First file's current-context wins (if set)
            if merged["current-context"] is None and cfg.get("current-context"):
                merged["current-context"] = cfg["current-context"]
            
            # Merge clusters (first occurrence of a name wins)
            for cluster in cfg.get("clusters", []):
                name = cluster.get("name")
                if name and name not in seen_clusters:
                    merged["clusters"].append(cluster)
                    seen_clusters.add(name)
            
            # Merge contexts (first occurrence of a name wins)
            for context in cfg.get("contexts", []):
                name = context.get("name")
                if name and name not in seen_contexts:
                    merged["contexts"].append(context)
                    seen_contexts.add(name)
            
            # Merge users (first occurrence of a name wins)
            for user in cfg.get("users", []):
                name = user.get("name")
                if name and name not in seen_users:
                    merged["users"].append(user)
                    seen_users.add(name)
                    
        except Exception:
            continue
    
    return merged

def get_current_namespace(kubeconfig=None):
    """
    Get the namespace from the current kubectl context.
    Returns the context's namespace, or 'default' if none is set.
    
    Args:
        kubeconfig: Optional pre-loaded kubeconfig dict. If None, loads via get_kubeconfig().
    
    Returns:
        str: The current namespace from kubectl context, or 'default'.
    """
    try:
        cfg = kubeconfig if kubeconfig is not None else get_kubeconfig()
        
        current_context = cfg.get("current-context")
        if not current_context:
            return "default"
        
        for ctx in cfg.get("contexts", []):
            if ctx.get("name") == current_context:
                return ctx.get("context", {}).get("namespace") or "default"
    except Exception:
        pass
    
    return "default"

def print_job_yaml(job_yaml, dry_run=False, verbose=False):
    """
    Print the YAML representation of a Kubernetes job configuration.

    Args:
        job_yaml (str): YAML representation of the Kubernetes job configuration.
        dry_run (bool): If True, indicates a dry run (no job submission).
        verbose (bool): If True, indicates verbose mode.
    """
    if dry_run:
        print("=" * 80)
        print("Dry run: Not submitting job.\nJob spec would be:")
        print("=" * 80)
        print(job_yaml)
        print("=" * 80 + "\n")
    elif verbose:
        print("=" * 80)
        print("Verbose mode: Job spec:")
        print("=" * 80)
        print(job_yaml)
        print("=" * 80 + "\n")
    else:
        pass

def submit_job(job_config, dry_run=False, verbose=False):

    job_yaml = yaml.dump(job_config, sort_keys=False, default_flow_style=False)

    print_job_yaml(job_yaml, dry_run=dry_run, verbose=verbose)
    if dry_run:
        return

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
        raise Exception(f"Error submitting job with subprocess: {e}")

def delete_resource(name, resource_type, namespace=None, kubectl_args=None):
    """
    Delete a Kubernetes job using kubectl.

    Args:
        name (str): Name of the resource.
        resource_type (str): Type of the resource (e.g., 'job', 'pod').
        namespace (str): Kubernetes namespace. If None, uses current kubectl context namespace.
        kubectl_args (list): Additional arguments to pass to kubectl delete.
    """
    namespace = namespace if namespace else get_current_namespace()
    kubectl_args = kubectl_args if kubectl_args else []

    try:
        logging.info(f"Deleting {resource_type} {name} in namespace {namespace}...")
        cmd = ['kubectl', 'delete', resource_type, name, '-n', namespace] + kubectl_args
        subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True
        )

        print(f"{resource_type} \x1b[1;32m{name}\x1b[0m \x1b[31mdeleted\x1b[0m from \x1b[38;5;245m{namespace}\x1b[0m namespace")

    except subprocess.CalledProcessError as e:
        # e.stderr contains the actual error message from kubectl
        error_msg = e.stderr.strip() if e.stderr else str(e)
        print(f"Error deleting {resource_type}/{name}: {error_msg}")

def forward_port_background(name, resource_type, host_port, pod_port, namespace=None):
    """
    Port forward a local port to a pod port using kubectl.

    Args:
        pod_name (str): Name of the pod.
        namespace (str): Kubernetes namespace. If None, uses current kubectl context namespace.
        local_port (int): Local port number.
        pod_port (int): Pod port number.
    """
    namespace = namespace if namespace else get_current_namespace()

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

def get_logs(pod_name, namespace=None, follow=True, timeout=None):
    """
    Follow logs of a pod using kr8s.

    Args:
        pod_name (str): Name of the pod.
        namespace (str): Kubernetes namespace. If None, uses current kubectl context namespace.
        follow (bool): Whether to follow the logs.
        timeout (int): Timeout in seconds for log streaming.
    """
    namespace = namespace if namespace else get_current_namespace()

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

        except (httpx.RemoteProtocolError, kr8s._exceptions.ServerError) as e:
            logging.warning(f"Log stream interrupted due to a connection error: {e}. Restarting log stream in 5 seconds...")
            time.sleep(5)

        except kr8s._exceptions.ConnectionClosedError as e:
            logging.warning(f"Connection closed error while streaming logs for pod {pod_name}: {e}. Restarting log stream in 5 seconds...")
            time.sleep(5)

        # Handle pod not found error
        except kr8s._exceptions.NotFoundError:
            logging.error(f"Pod {pod_name} not found to stream logs")
            break

        # Break the loop if timeout is reached
        except (httpx.ReadTimeout, kr8s._exceptions.APITimeoutError, TimeoutError):
            logging.error(f"Log stream timed out after {timeout} seconds. Stopping log stream.")
            break

        except KeyboardInterrupt:
            print("\nKeyboard interrupt received. Stopping log stream. But the job/pod will continue to run.")
            break

def get_job_pod_names(job_name, namespace=None, field_selector=None):
    """
    Get all active pod names associated with a Job (excluding terminating pods).
    
    Args:
        job_name (str): Name of the Job
        namespace (str): Kubernetes namespace. If None, uses current kubectl context namespace.
        field_selector (str): Additional field selector
    
    Returns:
        list: List of active pod names, sorted by creation time (newest first)
    """
    namespace = namespace if namespace else get_current_namespace()

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
        error_msg = e.stderr.strip() if e.stderr else str(e)
        logging.error(f"Error getting pods for job {job_name}: {error_msg}")
        return []
    except (json.JSONDecodeError, KeyError) as e:
        logging.error(f"Error parsing pod data for job {job_name}: {e}")
        return []

def _extract_pod_status(pod):
    """
    Extract detailed status info from a kr8s Pod object.
    """
    status = pod.status
    
    phase = status.get('phase', 'Unknown')
    reason = status.get('reason', '') 
    message = status.get('message', '')
    
    container_waiting_reason = None
    container_waiting_message = None
    container_terminated_reason = None
    container_terminated_exit_code = None
    is_ready = False
    
    # Check all container statuses (regular + init)
    all_container_statuses = (
        status.get('containerStatuses', []) + 
        status.get('initContainerStatuses', [])
    )
    
    for cs in all_container_statuses:
        state = cs.get('state', {})
        
        # Check waiting
        if 'waiting' in state and not container_waiting_reason:
            container_waiting_reason = state['waiting'].get('reason', '')
            container_waiting_message = state['waiting'].get('message', '')
        
        # Check terminated (OOMKilled, Error, etc.)
        if 'terminated' in state and not container_terminated_reason:
            term = state['terminated']
            if term.get('exitCode', 0) != 0 or term.get('reason') not in ('Completed', None):
                container_terminated_reason = term.get('reason', '')
                container_terminated_exit_code = term.get('exitCode')
    
    # Check Ready condition
    for condition in status.get('conditions', []):
        if condition.get('type') == 'Ready' and condition.get('status') == 'True':
            is_ready = True
            break
    
    return {
        'phase': phase,
        'reason': reason,
        'message': message,
        'container_waiting_reason': container_waiting_reason,
        'container_waiting_message': container_waiting_message,
        'container_terminated_reason': container_terminated_reason,
        'container_terminated_exit_code': container_terminated_exit_code,
        'is_ready': is_ready
    }


# Non-terminal waiting reasons that we should inform user about
_NON_TERMINAL_WAITING_REASONS = {
    'ImagePullBackOff': 'Image pull is failing',
    'ErrImagePull': 'Error pulling image',
    'CrashLoopBackOff': 'Container is crash-looping',
    'CreateContainerConfigError': 'Error creating container config',
    'InvalidImageName': 'Invalid image name specified'
}

# Transitional states that are normal and can be logged at info level
_TRANSITIONAL_STATES = {
    'ContainerCreating': 'Container is being created',
    'PodInitializing': 'Pod is initializing',
}

def _get_pod_events(pod_name, namespace, filter_warning=True):
    """Get events for a pod."""
    try:
        events = kr8s.get(
            "events",
            namespace=namespace,
            field_selector=f"involvedObject.name={pod_name},involvedObject.kind=Pod"
        )
        events_list = []
        for e in events:
            if filter_warning and e.raw.get('type') != 'Warning':
                continue
            if e.raw.get('reason') not in K8S_EVENTS:
                continue
            events_list.append({
                'reason': e.raw.get('reason', ''),
                'message': e.raw.get('message', '')
            })
        return events_list
    except Exception:
        return []


def _handle_pod_status(pod, last_reported_reasons, namespace=None, pods_events_checked=None):
    """
    Process pod status and return result.
    
    Args:
        pod: kr8s Pod object
        last_reported_reasons: The last waiting reason we reported to avoid spam for each pod
        namespace: Kubernetes namespace
        pods_events_checked: Set of pod names for which events have been checked (to avoid duplicate event checks)
    
    Returns:
        tuple: (result, new_last_reported_reason)
               result is 'running', 'succeeded', 'failed', or None (keep waiting)
    """
    status = _extract_pod_status(pod)
    phase = status['phase']
    pod_name = pod.name
    last_reported_reason = last_reported_reasons.get(pod_name)

    # Check pod events once per pod (before phase checks)
    if phase not in ('Running', 'Succeeded'):
        if pods_events_checked is not None and pod_name not in pods_events_checked:
            pod_warnings = _get_pod_events(pod_name, namespace)
            if pod_warnings:
                pods_events_checked.add(pod_name)
                for event in pod_warnings:
                    print(f"Pod {pod_name}: {event['reason']} - {event['message']}")

    if phase == 'Running':
        logging.info(f"Pod {pod_name} is Running.")
        return 'running', last_reported_reasons
    
    if phase == 'Succeeded':
        logging.info(f"Pod {pod_name} has Succeeded.")
        return 'succeeded', last_reported_reasons
    
    if phase == 'Failed':
        reason = status.get('reason') or status.get('container_waiting_reason') or 'Unknown'
        message = status.get('message') or status.get('container_waiting_message') or ''
        print(f"Pod {pod_name} has Failed. Reason: {reason}")
        if message:
            print(f"  Message: {message}")
        return 'failed', last_reported_reasons

    # Pending phase - check for waiting reasons
    if phase == 'Pending':
        waiting_reason = status.get('container_waiting_reason')
        if waiting_reason and waiting_reason != last_reported_reason:
            if waiting_reason in _NON_TERMINAL_WAITING_REASONS:
                desc = _NON_TERMINAL_WAITING_REASONS.get(waiting_reason, waiting_reason)
                print(f"Pod {pod_name}: {desc}")
                if status.get('container_waiting_message'):
                    print(f"  Details: {status['container_waiting_message']}")
            elif waiting_reason in _TRANSITIONAL_STATES:
                logging.info(
                    f"Pod {pod_name}: {_TRANSITIONAL_STATES.get(waiting_reason, waiting_reason)}")
            else:
                # Unknown waiting reason - still report it
                print(f"Pod {pod_name}: {waiting_reason}")
            last_reported_reason = waiting_reason
    
    # Unknown phase
    if phase == 'Unknown' and last_reported_reason != 'unknown':
        print(f"Pod {pod_name} is in Unknown state. This may indicate node issues.")
        last_reported_reason = 'unknown'

    # Check for OOMKilled or other container termination (while pod still "Running")
    if status.get('container_terminated_reason'):
        reason = status['container_terminated_reason']
        exit_code = status.get('container_terminated_exit_code', 'unknown')
        if reason == 'OOMKilled':
            print(f"Pod {pod_name}: Container was OOMKilled (exit code {exit_code})")
        elif reason != 'Completed':
            print(f"Pod {pod_name}: Container terminated with {reason} (exit code {exit_code})")

    last_reported_reasons[pod_name] = last_reported_reason

    return None, last_reported_reasons


def _get_job_status(job_name, namespace):
    """
    Get Job status to check if it has failed (backoffLimit reached) or succeeded.

    Args:
        job_name (str): Name of the job.
        namespace (str): Kubernetes namespace.
    
    Returns:
        dict with keys: 'active', 'succeeded', 'failed', 'complete', 'failed_permanently'
        Or None if job not found.
    """
    try:
        job = Job.get(job_name, namespace=namespace)
        status = job.status
        
        # Check conditions for Complete or Failed
        conditions = status.get('conditions', [])
        is_complete = False
        is_failed_permanently = False
        failure_reason = None
        
        for cond in conditions:
            if cond.get('type') == 'Complete' and cond.get('status') == 'True':
                is_complete = True
            if cond.get('type') == 'Failed' and cond.get('status') == 'True':
                is_failed_permanently = True
                failure_reason = cond.get('reason', '')
        
        return {
            'active': status.get('active', 0),
            'succeeded': status.get('succeeded', 0),
            'failed': status.get('failed', 0),
            'complete': is_complete,
            'failed_permanently': is_failed_permanently,
            'failure_reason': failure_reason,
        }
    except Exception:
        return None

def _get_job_events(job_name, namespace, filter_warning=True):
    """Get recent events for a job."""
    try:
        # Get the job's UID
        job = Job.get(job_name, namespace=namespace)
        job_uid = job.metadata.get('uid')

        events = kr8s.get(
            "events",
            namespace=namespace,
            field_selector=f"involvedObject.name={job_name},involvedObject.kind=Job"
        )
        
        events_list = []
        for e in events:
            if filter_warning and e.raw.get('type') != 'Warning':
                continue
            if e.raw.get('reason') not in K8S_EVENTS:
                continue

            if e.raw.get('involvedObject', {}).get('uid') == job_uid:
                events_list.append({
                    'reason': e.raw.get('reason', ''),
                    'message': e.raw.get('message', '')
                })
        return events_list
    
    except Exception:
        return []

def wait_for_job_pods_ready(job_name, namespace=None, timeout=300):
    """
    Wait for a Job pod to be in Running state, or handle terminal/failure states.
    Uses kr8s watch for efficient single-connection streaming updates.
    
    Behaviors:
    - If pod reaches Running state, return the pod name
    - If pod reaches Succeeded state, return the pod name
    - If pod fails, print logs and continue watching for retries/new pods
    - If Job reaches backoffLimit (permanent failure), return None
    - If pod is in a waiting state (ImagePullBackOff, etc.), inform user and keep waiting
    - Handle fast completion where pod goes to terminal state quickly

    Args:
        job_name (str): Name of the job.
        namespace (str): Kubernetes namespace. If None, uses current kubectl context namespace.
        timeout (int): Maximum time to wait in seconds.
    
    Returns:
        str: Pod name if pod reached running/succeeded, or None if failed/timeout.
    """
    namespace = namespace if namespace else get_current_namespace()
    start_time = time.time()
    last_reported_reasons = {}
    failed_pods_logged = set()  # Track pods we have already printed logs for
    pods_events_checked = set()  # Track pods for which we have checked events

    logging.info(f"Watching pods for job {job_name}...")

    # Before watch
    job_status = _get_job_status(job_name, namespace)
    if job_status is None:
        print(f"Job {job_name} not found in namespace {namespace}")
        return None
    
    # TODO: Should a small delay be added here to allow initial pod creation? Otherwise should one more watch for Job events be added?

    # Check if job already failed or has warning events
    # INFO: Checks for job events once before starting the watch. Any adverse events after that will not be reported.
    if job_status['failed_permanently']:
        print(f"Job {job_name} failed: {job_status['failure_reason']}")
        for event in _get_job_events(job_name, namespace):
            print(f"{event['reason']}: {event['message']}")
        return None
    
    # Even if not failed yet, warn about issues
    # INFO: Checks for job events once before starting the watch. Any adverse events after that will not be reported.
    warning_events = _get_job_events(job_name, namespace)
    if warning_events and job_status['active'] == 0:
        print(f"Job {job_name} has warnings and no active pods:")
        for event in warning_events:
            print(f"{event['reason']}: {event['message']}")

    try:
        # Use kr8s to watch pods with the job-name label selector
        # This opens a single persistent connection and receives push updates
        for event, pod in kr8s.watch(
            "pods",
            namespace=namespace,
            label_selector=f"job-name={job_name}",
        ):
            # Check timeout
            elapsed = time.time() - start_time
            if elapsed > timeout:
                print(f"Timeout waiting for job {job_name} pods after {timeout}s.")
                return None

            # Skip DELETED events
            if event == "DELETED":
                logging.debug(f"Pod {pod.name} was deleted.")
                # Check if job still exists
                # INFO: This currently only checks if job is deleted when atleast one pod has been initialized and then deleted.
                # INFO: If the job is deleted before any pod is created, the watch will not receive any pod events and will timeout.
                # INFO: Not checking for job deletion on MODIFIED events to avoid excessive API calls.
                job_status = _get_job_status(job_name, namespace)
                if job_status is None:
                    print(f"Job {job_name} was deleted.")
                    return None
                continue

            # Process ADDED and MODIFIED events
            # INFO: This prints warnings if they are in pending mode due to some issue. However, this only checks once for events per pod. 
            # INFO: So this might miss some future events. Event watching can be added later if needed.
            result, last_reported_reasons = _handle_pod_status(pod, last_reported_reasons, namespace, pods_events_checked)
            
            if result == 'running':
                return pod.name
            
            elif result == 'succeeded':
                logging.info(f"Pod {pod.name} completed successfully (Succeeded).")
                return pod.name
            
            elif result == 'failed':
                # Pod failed - print logs if we haven't already
                if pod.name not in failed_pods_logged:
                    print(f"Pod {pod.name} failed. Printing logs...")
                    get_logs(pod.name, namespace, follow=False, timeout=30)
                    failed_pods_logged.add(pod.name)
                
                    # Check if Job has permanently failed (backoffLimit reached)
                    job_status = _get_job_status(job_name, namespace)
                    if job_status:
                        if job_status['failed_permanently']:
                            reason = job_status.get('failure_reason', 'BackoffLimitExceeded')
                            print(f"Job {job_name} has permanently failed. Reason: {reason}")
                            return None
                        elif job_status['active'] > 0:
                            print(f"Job has {job_status['active']} active pod(s). Continuing to watch...")
                        else:
                            # No active pods, but job not marked as failed yet
                            # Could be creating a new pod, continue watching
                            logging.info(f"No active pods for job {job_name}, waiting for new pod or job failure...")

    except KeyboardInterrupt:
        print("\nInterrupted while waiting for pod.")
        return None
    
    except Exception as e:
        import traceback
        logging.error(f"Error watching pods for job {job_name}: {e}")
        traceback.print_exc()
        return None

def wait_for_pod_ready(pod_name, namespace=None, timeout=300):
    """
    Wait for a Kubernetes pod to be in the 'Running' state, or handle terminal states.
    Uses kr8s watch for efficient single-connection streaming updates.
    
    Behaviors:
    - Returns 'running' if pod reaches Running state
    - Returns 'succeeded' if pod completes successfully
    - Returns 'failed' if pod fails
    - Returns 'timeout' if timeout exceeded
    - Prints status updates for waiting states (ImagePullBackOff, CrashLoopBackOff, etc.)

    Args:
        pod_name (str): Name of the pod.
        namespace (str): Kubernetes namespace. If None, uses current kubectl context namespace.
        timeout (int): Maximum time to wait in seconds.
    
    Returns:
        str: 'running', 'succeeded', 'failed', or 'timeout'
    """
    namespace = namespace if namespace else get_current_namespace()
    start_time = time.time()
    last_reported_reasons = {}

    logging.info(f"Watching pod {pod_name} for ready state...")

    try:
        # Use kr8s to watch a specific pod by field selector
        for event, pod in kr8s.watch(
            "pods",
            namespace=namespace,
            field_selector=f"metadata.name={pod_name}",
        ):
            # Check timeout
            elapsed = time.time() - start_time
            if elapsed > timeout:
                print(f"Timeout waiting for pod {pod_name} after {timeout}s.")
                return 'timeout'

            # Skip DELETED events
            if event == "DELETED":
                logging.warning(f"Pod {pod_name} was deleted while waiting.")
                return 'failed'

            # Process ADDED and MODIFIED events
            result, last_reported_reasons = _handle_pod_status(pod, last_reported_reasons)
            
            if result is not None:
                return result

    except KeyboardInterrupt:
        print("\nInterrupted while waiting for pod.")
        return 'timeout'
    except Exception as e:
        logging.error(f"Error watching pod {pod_name}: {e}")
        return 'failed'

def get_shell_from_container_spec(pod_name, namespace=None, container_name=None):
    """Check if container spec specifies a shell. If namespace is None, uses current kubectl context namespace."""
    
    namespace = namespace if namespace else get_current_namespace()
    
    try:
        cmd = ["kubectl", "get", "pod", pod_name, "-n", namespace, "-o", "json"]
        result = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True,
            timeout=10,
            check=True
        )
        pod_spec = json.loads(result.stdout)
        
        containers = pod_spec.get("spec", {}).get("containers", [])
        if not containers:
            return None
            
        if container_name:
            container = next((c for c in containers if c["name"] == container_name), None)
            if not container:
                container = containers[0]
        else:
            container = containers[0]
        
        # Check command for shell specification
        command = container.get("command", [])
        if command:
            for cmd_part in command:
                if "bash" in str(cmd_part):
                    return "/bin/bash"
                elif "zsh" in str(cmd_part):
                    return "/usr/bin/zsh"
                elif str(cmd_part) in ["/bin/sh", "sh"]:
                    return "/bin/sh"
        
        return None
        
    except Exception:
        return None


def detect_shell(pod_name, namespace=None, container_name=None):
    """Detect best available shell. If namespace is None, uses current kubectl context namespace."""

    namespace = namespace if namespace else get_current_namespace()
    
    # First, check if spec tells us
    spec_shell = get_shell_from_container_spec(pod_name, namespace, container_name)
    if spec_shell:
        return spec_shell
    
    # Otherwise, probe the container
    base_cmd = ["kubectl", "exec", pod_name, "-n", namespace]
    if container_name:
        base_cmd += ["-c", container_name]
    
    shells = ["/bin/bash", "/usr/bin/zsh", "/usr/bin/fish", "/bin/sh"]
    
    for shell in shells:
        try:
            result = subprocess.run(
                base_cmd + ["--", "test", "-x", shell],
                capture_output=True,
                timeout=2
            )
            logging.debug(f"Probing for shell {shell}, result code: {result}")
            if result.returncode == 0:
                return shell
        except Exception:
            continue
    
    return "/bin/sh"

def exec_into_pod(pod_name, namespace=None, shell='/bin/sh', container_name=None):
    """
    Exec into a Kubernetes pod using kubectl.

    Args:
        pod_name (str): Name of the pod.
        namespace (str): Kubernetes namespace. If None, uses current kubectl context namespace.
        shell (str): Shell to use inside the pod.
        container_name (str, optional): Container name for multi-container pods.
    """

    namespace = namespace if namespace else get_current_namespace()
    
    try:
        logging.info(f"Executing into pod {pod_name} in namespace {namespace} with shell {shell}...")
        
        cmd = ['kubectl', 'exec', '-it', pod_name, '-n', namespace]
        if container_name:
            cmd += ['-c', container_name]
        cmd += ['--', shell]
        
        result = subprocess.run(cmd, check=False)

        # Exit code 130 = user pressed Ctrl+C in the shell (normal)
        if result.returncode == 130:
            return
        
        # Exit code 137 = pod terminated/killed
        if result.returncode == 137:
            raise Exception(f"Pod {pod_name} is terminated (exit code 137). Cannot exec into it.")
        
        # Exit code 126 = shell/command not executable
        if result.returncode == 126:
            raise Exception(f"Shell {shell} is not executable in pod {pod_name}")
        
        # Exit code 127 = shell/command not found
        if result.returncode == 127:
            raise Exception(f"Shell {shell} not found in pod {pod_name}")
        
        if result.returncode != 0:
            raise Exception(f"kubectl exec failed with exit code {result.returncode}")
        
    except KeyboardInterrupt:
        # User hit Ctrl+C while exec was starting (before entering shell)
        return
    except Exception as e:
        raise Exception(e)

class TemplateInfo:
    TEMPLATE_RE = re.compile(
        r"^(?P<job_name>.+)_(?P<job_type>[^_]+)_template_(?P<ts>[0-9]{8}-[0-9]{6}-[0-9]{6})\.(?P<ext>yaml|yml)$",
        re.IGNORECASE,
    )

    def __init__(self, path, job_name, job_type, timestamp):
        self.path = path
        self.job_name = job_name
        self.job_type = job_type
        self.timestamp = timestamp

    @classmethod
    def from_path(cls, p):
        m = cls.TEMPLATE_RE.match(p.name)
        if not m:
            return None
        ts_txt = m.group("ts")
        try:
            ts = datetime.strptime(ts_txt, "%Y%m%d-%H%M%S-%f").replace(tzinfo=timezone.utc)
        except Exception:
            ts = None

        # Only base name is stored in path
        return cls(path=p.name, job_name=m.group("job_name"), job_type=m.group("job_type"), timestamp=ts)

class TemplateManager():
    def __init__(self, templates_dir=None):
        if templates_dir is None:
            self.templates_dir = JET_HOME / "templates"
        else:
            self.templates_dir = Path(templates_dir)
        self.templates_dir.mkdir(parents=True, exist_ok=True)
        self.TS_RE = re.compile(r"_template_(?P<ts>\d{8}-\d{6}-\d{6})\.(yaml|yml)$")

    def save_job_template(self, job_config, job_name, job_type, verbose= False):
        print_job_yaml(yaml.dump(job_config, sort_keys=False, default_flow_style=False),
                    verbose=verbose)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
        filename = f"{job_name}_{job_type}_template_{timestamp}.yaml"
        job_yaml_path = self.templates_dir / filename
        # Write YAML
        with job_yaml_path.open("w") as f:
            yaml.dump(job_config, f, sort_keys=False, default_flow_style=False)

        print(f"Job template saved to {job_yaml_path}")
        return str(job_yaml_path)

    def resolve_template_path(self, template_arg: str, job_type: str) -> str:
        """
        Resolve either:
        - a path to an existing YAML file (absolute or relative), or
        - a template name (job_name) which will be searched in ~/.local/share/jet/templates/ or $XDG_DATA_HOME/jet/templates/
            matching: {job_name}_{job_type}_template_*.yaml or *.yml
        Returns the absolute path to the template file as a string.
        Raises ValueError if nothing matches.
        """
        # Treat input as a path first (expand ~ and relative)
        candidate = Path(template_arg).expanduser().resolve()
        if candidate.is_file():
            return str(candidate)

        # Fallback: search ~/.local/share/jet/templates/ or $XDG_DATA_HOME/jet/templates/ for matching template files
        if not self.templates_dir.is_dir():
            raise ValueError(f"Template directory not found: {self.templates_dir}. Please ensure it exists.")

        # Use stem of template_arg to accept inputs like "foo", "foo.yaml", or "dir/foo"
        job_name_stem = Path(template_arg).stem
        prefix = f"{job_name_stem}_{job_type}_template_"

        # Gather matches (only files), support .yaml and .yml
        matches = [p for p in self.templates_dir.iterdir()
                if p.is_file() and p.suffix.lower() in (".yaml", ".yml") and p.name.startswith(prefix)]

        if not matches:
            raise ValueError(
                f"No templates named {job_name_stem} found in {self.templates_dir} for job type {job_type}. "
                "Provide a valid template name saved in ~/.local/share/jet/templates/ or $XDG_DATA_HOME/jet/templates/ or a full path to a job yaml file."
            )

        latest = max(matches, key=lambda p: p.stat().st_mtime)
        return str(latest)

    def _discover_all(self):
        infos = []
        for p in self.templates_dir.iterdir():
            if not p.is_file():
                continue
            ti = TemplateInfo.from_path(p)
            if ti:
                infos.append(ti)
        return infos
        
    def _ts_from_template_info(self, ti):
        """
        Extract timestamp from template info (the one you write into templates).
        Return a timezone-aware datetime in UTC if parse succeeds.
        If parsing fails, fallback to filesystem mtime (UTC).
        If that also fails, return epoch (1970-01-01 UTC).
        """
        if ti.timestamp is not None:
            return ti.timestamp

        # fallback to filesystem mtime if timestamp not present
        try:
            return datetime.fromtimestamp(Path(ti.path).stat().st_mtime, tz=timezone.utc)
        except Exception:
            return datetime.fromtimestamp(0, tz=timezone.utc)

    def list_templates(self, job_type=None, verbose=False,
                   filter_by=None, filter_regex=None,
                   sort_by="name"):
        """
        Returns structure:
            { job_type: { job_name: { "paths": [str,...], "latest": str } } }

        Behavior:
        - All versions of a template (same job_name) are ALWAYS sorted by timestamp (newest first)
        - "latest" is ALWAYS computed by timestamp
        - sort_by="time" sorts job_name groups (different templates) by their latest timestamp
        - sort_by="name" sorts job_name groups alphabetically
        """
        infos = self._discover_all()  # list[TemplateInfo]
        if job_type:
            job_type = job_type.lower()

        regex = re.compile(filter_regex) if filter_regex else None

        # grouped: job_type -> job_name -> {"versions": [(path, ts), ...], "_latest_ts": datetime}
        grouped = defaultdict(lambda: defaultdict(lambda: {"versions": []}))

        # Build grouped structure once with timestamps
        for ti in infos:
            if job_type and ti.job_type.lower() != job_type:
                continue
            if filter_by and filter_by not in ti.job_name:
                continue
            if regex and not regex.search(ti.job_name):
                continue

            # Determine timestamp: use parsed timestamp from TemplateInfo when available,
            # otherwise fall back to filesystem mtime (UTC), otherwise epoch.
            ts = self._ts_from_template_info(ti)

            grouped[ti.job_type][ti.job_name]["versions"].append((str(ti.path), ts))

        # For each job_name sort versions newest-first and set latest & _latest_ts
        for jtype, jobs in grouped.items():
            for jname, info in jobs.items():
                versions = info.get("versions", [])

                # Sort newest-first by timestamp (deterministic)
                versions.sort(key=lambda x: x[1], reverse=True)

                # Write back 'paths' list (newest -> oldest)
                info["paths"] = [p for p, _ in versions]

                # Set latest path and its timestamp for job-level sorting
                if versions:
                    info["latest"] = versions[0][0]
                    info["_latest_ts"] = versions[0][1]
                else:
                    info["latest"] = None
                    info["_latest_ts"] = None

        # Sort job_name groups according to sort_by and drop ephemeral keys
        for jtype, jobs in list(grouped.items()):
            if sort_by == "time":
                # Sort job_names by their latest ts (newest job_name first)
                sorted_items = sorted(
                    jobs.items(),
                    key=lambda kv: (kv[1].get("_latest_ts") is not None, kv[1].get("_latest_ts")),
                    reverse=True,
                )
            else:
                # sort by job_name lexicographically
                sorted_items = sorted(jobs.items(), key=lambda kv: kv[0])

            new_jobs = {}
            for jname, info in sorted_items:
                # Remove helper fields before returning
                info.pop("_latest_ts", None)
                # Keep only paths and latest (latest only if verbose or you always want it)
                if not verbose:
                    info.pop("paths", None)
                # Remove versions list (we exposed paths instead)
                info.pop("versions", None)
                new_jobs[jname] = info

            grouped[jtype] = new_jobs

        # If job_type requested, return just that subsection
        return grouped.get(job_type, {}) if job_type else grouped
    
    def print_templates(self, job_type=None, verbose=False,
                        filter_by=None, filter_regex=None,
                        sort_by="name"):
        templates = self.list_templates(
            job_type=job_type,
            verbose=verbose,
            filter_by=filter_by,
            filter_regex=filter_regex,
            sort_by=sort_by
        )

        if not templates:
            print("No templates found")
            return

        # If verbose, print all paths and mark latest
        templates_dict = {}
        for jtype, jobs in templates.items():
            templates_dict[jtype] = {}
            for jname, info in jobs.items():
                if verbose:
                    paths_info = []
                    for p in info.get("paths", []):
                        mark = " (latest)" if p == info.get("latest") else ""
                        paths_info.append(f"{p}{mark}")
                    templates_dict[jtype][jname] = paths_info
                else:
                    mark = " (latest)" if info.get("latest") else ""
                    templates_dict[jtype][jname] = f"{info.get('latest', 'None')}{mark}"
        print_tables_wrapped(templates_dict, headers=["Job Type", "Template Name", "Template(s)"], padding=4)
    
    # TODO: add delete_template method
    # TODO: add clear_templates method

# Pretty print functions (for listing templates and other items)
def _is_scalar(x):
    return not isinstance(x, (dict, list))

def _gather_rows(obj, path, rows):
    """
    Args:
        obj: nested dict/list/scalar
        path: list of keys representing the current path in the nested structure
        rows: list to append the gathered rows to
    """
    if isinstance(obj, dict):
        for k, v in obj.items():
            _gather_rows(v, path + [str(k)], rows)
    elif isinstance(obj, list):
        for item in obj:
            if _is_scalar(item):
                rows.append(path + [str(item)])
            else:
                _gather_rows(item, path, rows)
    else:
        rows.append(path + [str(obj)])

def print_tables_wrapped(data,
                         headers=None,
                         max_total_width=None,
                         padding=2,
                         min_col_width=8):
    """
    Print an arbitrarily-nested mapping `data` as a merged-column table with wrapping.

    Args:
      data: nested mapping (dict -> dict -> ... -> list/string)
      headers: optional list of header strings; auto-generates Head1..N if omitted
      max_total_width: optional total width to fit the table into (defaults to terminal width)
      padding: spaces between columns
      min_col_width: minimum width allowed for a column after distribution
    """
    # 1) gather rows (each row is a list of column values)
    rows = []
    _gather_rows(data, [], rows)
    if not rows:
        print("(no data)")
        return

    # 2) normalize row lengths to same number of columns
    max_cols = max(len(r) for r in rows)
    for r in rows:
        if len(r) < max_cols:
            r.extend([""] * (max_cols - len(r)))

    # 3) build headers
    if headers:
        if len(headers) < max_cols:
            headers = list(headers) + [f"Head{i}" for i in range(len(headers)+1, max_cols+1)]
        else:
            headers = list(headers[:max_cols])
    else:
        headers = [f"Head{i}" for i in range(1, max_cols+1)]

    # 4) available width
    term_w = shutil.get_terminal_size((120, 30)).columns
    total_w = max_total_width or term_w
    # reserved for paddings between columns
    total_padding = padding * (max_cols - 1)
    usable = max(total_w - total_padding, max_cols * min_col_width)

    # 5) compute initial natural column widths (max of header and content lengths)
    natural = []
    for c in range(max_cols):
        w = len(str(headers[c]))
        for r in rows:
            w = max(w, len(str(r[c])))
        natural.append(w)

    # 6) if sum(natural) <= usable, use natural widths; else scale down proportionally but enforce min_col_width
    sum_nat = sum(natural)
    if sum_nat <= usable:
        col_widths = natural
    else:
        # proportional shrink
        col_widths = [max(min_col_width, int(n * usable / sum_nat)) for n in natural]
        # fix rounding so sum(col_widths) == usable by distributing leftover
        cur_sum = sum(col_widths)
        i = 0
        while cur_sum < usable:
            col_widths[i % max_cols] += 1
            cur_sum += 1
            i += 1
        while cur_sum > usable:
            # reduce where possible
            for j in range(max_cols):
                if col_widths[j] > min_col_width and cur_sum > usable:
                    col_widths[j] -= 1
                    cur_sum -= 1
                if cur_sum == usable:
                    break

    # 7) prepare wrapped cell cache: for each row and col produce list[str] lines
    wrapped_rows = []
    for r in rows:
        wrapped_row = []
        for i, cell in enumerate(r):
            txt = "" if cell is None else str(cell)
            # wrap, preserving words; ensure at least one line
            wrapped = textwrap.wrap(txt, width=col_widths[i]) or [""]
            wrapped_row.append(wrapped)
        wrapped_rows.append(wrapped_row)

    # 8) prepare header wrapped (single-line headers padded)
    header_cells = [headers[i].ljust(col_widths[i]) for i in range(max_cols)]
    header_line = (" " * padding).join(header_cells)
    print(header_line)
    print("-" * min(total_w, len(header_line)))

    # 9) printing rows while suppressing repeated cells vertically:
    prev_full = [""] * max_cols  # store full original cell text used to decide repeat suppression

    for wrapped_row in wrapped_rows:
        # compute number of physical lines this logical row will expand to
        height = max(len(wrapped_row[i]) for i in range(max_cols))

        # for each column determine whether it should print or be blank (compare full cell text to prev)
        will_print = []
        full_texts = ["\n".join(wrapped_row[i]) for i in range(max_cols)]
        for i in range(max_cols):
            if full_texts[i] != prev_full[i]:
                # we will print this column's wrapped block (height lines), and reset lower prevs
                will_print.append(True)
                prev_full[i] = full_texts[i]
                # reset lower-level prevs so they reappear when higher changes
                for j in range(i+1, max_cols):
                    prev_full[j] = ""
            else:
                will_print.append(False)

        # Now print the physical lines (0..height-1)
        for line_idx in range(height):
            out_cells = []
            for i in range(max_cols):
                if will_print[i]:
                    lines = wrapped_row[i]
                    cell_line = lines[line_idx] if line_idx < len(lines) else ""
                    out_cells.append(cell_line.ljust(col_widths[i]))
                else:
                    # column suppressed (same as previous), print blanks of column width
                    out_cells.append(" " * col_widths[i])
            print((" " * padding).join(out_cells))