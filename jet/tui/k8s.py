"""Kubernetes client for fetching jobs, pods, logs, and describe info."""
import subprocess
import json
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field

from ..utils import get_current_namespace


@dataclass
class PodInfo:
    """Pod information similar to k9s display."""
    name: str
    namespace: str
    ready: str  # e.g., "1/1"
    status: str
    restarts: int
    cpu: str
    cpu_percent_request: str
    cpu_percent_limit: str
    memory: str
    memory_percent_request: str
    memory_percent_limit: str
    ip: str
    node: str
    age: str
    created_at: datetime
    labels: Dict[str, str] = field(default_factory=dict)
    port_forward: bool = False  # PF indicator
    job_name: Optional[str] = None
    

@dataclass
class JobInfo:
    """Job information similar to k9s display."""
    name: str
    namespace: str
    completions: str  # e.g., "0/1"
    duration: str
    age: str
    created_at: datetime
    status: str = ""
    labels: Dict[str, str] = field(default_factory=dict)
    active: int = 0
    succeeded: int = 0
    failed: int = 0
    start_time: Optional[datetime] = None  # For duration calculation
    completion_time: Optional[datetime] = None  # None if still running


def format_duration(start_time: Optional[datetime], completion_time: Optional[datetime]) -> str:
    """
    Format duration like kubectl using Kubernetes HumanDuration logic.
    
    Args:
        start_time: Start time of the duration
        completion_time: End time of the duration (None means now)
    
    Returns:
        Formatted duration string (e.g., "5m30s", "2d", "3y45d")
    """
    if not start_time:
        return "<none>"
    
    end_time = completion_time or datetime.now(timezone.utc)
    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=timezone.utc)
    if end_time.tzinfo is None:
        end_time = end_time.replace(tzinfo=timezone.utc)
    
    delta = end_time - start_time
    total_seconds = int(delta.total_seconds())
    
    if total_seconds < -1:
        return "<invalid>"
    elif total_seconds < 0:
        return "0s"
    elif total_seconds < 120:  # < 2 minutes
        return f"{total_seconds}s"
    
    minutes = total_seconds // 60
    if minutes < 10:  # 2-10 minutes
        seconds = total_seconds % 60
        if seconds > 0:
            return f"{minutes}m{seconds}s"
        return f"{minutes}m"
    elif minutes < 180:  # 10-180 minutes (3 hours)
        return f"{minutes}m"
    
    hours = total_seconds // 3600
    if hours < 8:  # 3-8 hours
        mins = (total_seconds % 3600) // 60
        if mins > 0:
            return f"{hours}h{mins}m"
        return f"{hours}h"
    elif hours < 48:  # 8-48 hours
        return f"{hours}h"
    elif hours < 192:  # 2-8 days
        days = hours // 24
        remaining_hours = hours % 24
        if remaining_hours > 0:
            return f"{days}d{remaining_hours}h"
        return f"{days}d"
    elif hours < 24 * 365 * 2:  # 8 days - 2 years
        return f"{hours // 24}d"
    elif hours < 24 * 365 * 8:  # 2-8 years
        days = hours // 24
        years = days // 365
        remaining_days = days % 365
        if remaining_days > 0:
            return f"{years}y{remaining_days}d"
        return f"{years}y"
    else:  # 8+ years
        years = hours // (24 * 365)
        return f"{years}y"

def format_age(created_at: datetime) -> str:
    """
    Format age (time since creation) like kubectl.
    
    This is a convenience wrapper around format_duration where the end time is "now".
    
    Args:
        created_at: Creation timestamp
    
    Returns:
        Formatted age string (e.g., "5m30s", "2d", "3y45d")
    """
    return format_duration(created_at, None)

def parse_datetime(dt_str: Optional[str]) -> Optional[datetime]:
    """Parse Kubernetes datetime string."""
    if not dt_str:
        return None
    try:
        # Handle both formats
        if dt_str.endswith('Z'):
            return datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
        return datetime.fromisoformat(dt_str)
    except (ValueError, TypeError):
        return None


class K8sClient:
    """Lightweight Kubernetes client using kubectl."""
    
    def __init__(self, namespace: Optional[str] = None):
        self.namespace = namespace or get_current_namespace()
        self._metrics_available: Optional[bool] = None
        self._active_processes: List[subprocess.Popen] = []  # Track active log streaming processes
    
    def kill_active_processes(self) -> None:
        """Kill all active log streaming processes."""
        for proc in self._active_processes:
            if proc and proc.poll() is None:
                try:
                    proc.kill()
                    proc.wait(timeout=0.5)
                except:
                    pass
        self._active_processes.clear()
    
    def _run_kubectl(self, args: List[str], timeout: int = 30) -> Optional[str]:
        """Run kubectl command and return output."""
        try:
            cmd = ['kubectl'] + args
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            if result.returncode == 0:
                return result.stdout
            return None
        except (subprocess.TimeoutExpired, subprocess.SubprocessError):
            return None
    
    def _check_metrics_available(self) -> bool:
        """Check if metrics-server is available."""
        if self._metrics_available is None:
            output = self._run_kubectl(['top', 'pods', '-n', self.namespace, '--no-headers'], timeout=5)
            self._metrics_available = output is not None
        return self._metrics_available
    
    def get_jobs(self, namespace: Optional[str] = None) -> List[JobInfo]:
        """Get all jobs in namespace."""
        ns = namespace or self.namespace
        output = self._run_kubectl([
            'get', 'jobs',
            '-n', ns,
            '-o', 'json'
        ])
        
        if not output:
            return []
        
        try:
            data = json.loads(output)
            jobs = []
            
            for item in data.get('items', []):
                metadata = item.get('metadata', {})
                status = item.get('status', {})
                spec = item.get('spec', {})
                
                name = metadata.get('name', '')
                created_str = metadata.get('creationTimestamp', '')
                created_at = parse_datetime(created_str) or datetime.now(timezone.utc)
                
                # Completions
                succeeded = status.get('succeeded', 0) or 0
                failed = status.get('failed', 0) or 0
                active = status.get('active', 0) or 0
                completions = spec.get('completions', 1) or 1
                completions_str = f"{succeeded}/{completions}"
                
                # Duration
                start_time = parse_datetime(status.get('startTime'))
                completion_time = parse_datetime(status.get('completionTime'))
                duration = format_duration(start_time, completion_time)
                
                # Status determination
                conditions = status.get('conditions', [])
                job_status = ""
                for cond in conditions:
                    if cond.get('type') == 'Complete' and cond.get('status') == 'True':
                        job_status = "Complete"
                        break
                    elif cond.get('type') == 'Failed' and cond.get('status') == 'True':
                        job_status = "Failed"
                        break
                    elif cond.get('type') == 'Suspended' and cond.get('status') == 'True':
                        job_status = "Suspended"
                        break
                
                if not job_status:
                    if active > 0:
                        job_status = "Running"
                    elif succeeded >= completions:
                        job_status = "Complete"
                    elif failed > 0:
                        job_status = "Failed"
                    else:
                        job_status = "Pending"
                
                jobs.append(JobInfo(
                    name=name,
                    namespace=ns,
                    completions=completions_str,
                    duration=duration,
                    age=format_age(created_at),
                    created_at=created_at,
                    status=job_status,
                    labels=metadata.get('labels', {}),
                    active=active,
                    succeeded=succeeded,
                    failed=failed
                ))
            
            # Sort by creation time (newest first)
            jobs.sort(key=lambda j: j.created_at, reverse=True)
            return jobs
            
        except (json.JSONDecodeError, KeyError):
            return []
    
    def get_pods(self, namespace: Optional[str] = None, job_name: Optional[str] = None) -> List[PodInfo]:
        """Get pods, optionally filtered by job."""
        ns = namespace or self.namespace
        args = ['get', 'pods', '-n', ns, '-o', 'json']
        
        if job_name:
            args.extend(['--selector', f'job-name={job_name}'])
        
        output = self._run_kubectl(args)
        
        if not output:
            return []
        
        try:
            data = json.loads(output)
            pods = []
            
            for item in data.get('items', []):
                metadata = item.get('metadata', {})
                status = item.get('status', {})
                spec = item.get('spec', {})
                
                name = metadata.get('name', '')
                created_str = metadata.get('creationTimestamp', '')
                created_at = parse_datetime(created_str) or datetime.now(timezone.utc)
                
                # Check if pod is terminating (has deletionTimestamp)
                is_terminating = metadata.get('deletionTimestamp') is not None
                
                # Ready status
                container_statuses = status.get('containerStatuses', [])
                ready_count = sum(1 for cs in container_statuses if cs.get('ready', False))
                total_containers = len(container_statuses) or len(spec.get('containers', []))
                ready_str = f"{ready_count}/{total_containers}"
                
                # Pod status - more detailed like k9s
                phase = status.get('phase', 'Unknown')
                pod_status = phase
                
                # If terminating, show that status
                if is_terminating:
                    pod_status = "Terminating"
                # Check for more specific status from container statuses
                elif container_statuses:
                    for cs in container_statuses:
                        state = cs.get('state', {})
                        if 'waiting' in state:
                            reason = state['waiting'].get('reason', '')
                            if reason:
                                pod_status = reason
                                break
                        elif 'terminated' in state:
                            reason = state['terminated'].get('reason', '')
                            exit_code = state['terminated'].get('exitCode', 0)
                            if reason:
                                pod_status = reason
                            elif exit_code != 0:
                                pod_status = f"Error({exit_code})"
                            break
                        elif 'running' in state:
                            # Check if ready
                            if not cs.get('ready', False):
                                pod_status = "NotReady"
                
                # Check init container statuses
                init_container_statuses = status.get('initContainerStatuses', [])
                for cs in init_container_statuses:
                    state = cs.get('state', {})
                    if 'waiting' in state:
                        reason = state['waiting'].get('reason', '')
                        if reason:
                            pod_status = f"Init:{reason}"
                            break
                    elif 'terminated' in state:
                        exit_code = state['terminated'].get('exitCode', 0)
                        if exit_code != 0:
                            pod_status = f"Init:Error"
                            break
                
                # Restarts
                restarts = sum(cs.get('restartCount', 0) for cs in container_statuses)
                
                # IP and Node
                pod_ip = status.get('podIP', '<none>') or '<none>'
                node_name = spec.get('nodeName', '<none>') or '<none>'
                
                # Extract job name from labels
                labels = metadata.get('labels', {})
                pod_job_name = labels.get('job-name', '')
                
                pods.append(PodInfo(
                    name=name,
                    namespace=ns,
                    ready=ready_str,
                    status=pod_status,
                    restarts=restarts,
                    cpu="0",  # Would need metrics-server
                    cpu_percent_request="0",
                    cpu_percent_limit="0",
                    memory="0",
                    memory_percent_request="0",
                    memory_percent_limit="0",
                    ip=pod_ip,
                    node=node_name,
                    age=format_age(created_at),
                    created_at=created_at,
                    labels=labels,
                    job_name=pod_job_name
                ))
            
            # Sort by creation time (newest first)
            pods.sort(key=lambda p: p.created_at, reverse=True)
            return pods
            
        except (json.JSONDecodeError, KeyError):
            return []
    
    def get_pod_metrics(self, namespace: Optional[str] = None) -> Dict[str, Dict[str, str]]:
        """Get pod metrics from metrics-server."""
        ns = namespace or self.namespace
        
        if not self._check_metrics_available():
            return {}
        
        output = self._run_kubectl([
            'top', 'pods',
            '-n', ns,
            '--no-headers'
        ], timeout=10)
        
        if not output:
            return {}
        
        metrics = {}
        for line in output.strip().split('\n'):
            parts = line.split()
            if len(parts) >= 3:
                pod_name = parts[0]
                cpu = parts[1].replace('m', '')  # Remove millicores suffix
                memory = parts[2].replace('Mi', '').replace('Gi', '')
                metrics[pod_name] = {'cpu': cpu, 'memory': memory}
        
        return metrics
    
    def get_logs(self, pod_name: str, namespace: Optional[str] = None, 
                 follow: bool = False, tail: int = 100, 
                 container: Optional[str] = None) -> Optional[str]:
        """Get pod logs."""
        ns = namespace or self.namespace
        args = ['logs', pod_name, '-n', ns, f'--tail={tail}']
        
        if container:
            args.extend(['-c', container])
        
        # Note: follow mode is handled separately with streaming
        output = self._run_kubectl(args, timeout=30)
        return output
    
    def stream_logs(self, pod_name: str, namespace: Optional[str] = None,
                    container: Optional[str] = None, tail: int = 100):
        """Stream logs from a pod (generator). Process can be killed via kill_active_processes()."""
        ns = namespace or self.namespace
        args = ['kubectl', 'logs', pod_name, '-n', ns, '-f', f'--tail={tail}']
        
        if container:
            args.extend(['-c', container])
        
        process = None
        try:
            process = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1  # Line buffered
            )
            
            # Track this process so it can be killed externally
            self._active_processes.append(process)
            
            # Use blocking readline - process will be killed externally if needed
            for line in iter(process.stdout.readline, ''):
                if process.poll() is not None:
                    # Process was killed
                    break
                yield line.rstrip('\n')
            
            process.wait()
                
        except GeneratorExit:
            pass
        except (subprocess.SubprocessError, OSError):
            pass
        finally:
            if process:
                # Remove from active list
                if process in self._active_processes:
                    self._active_processes.remove(process)
                # Kill if still running
                if process.poll() is None:
                    process.kill()
                    try:
                        process.wait(timeout=1)
                    except:
                        pass
    
    def describe(self, resource_type: str, name: str, 
                 namespace: Optional[str] = None) -> Optional[str]:
        """Get describe output for a resource."""
        ns = namespace or self.namespace
        output = self._run_kubectl([
            'describe', resource_type, name,
            '-n', ns
        ], timeout=30)
        return output
    
    def get_job_logs(self, job_name: str, namespace: Optional[str] = None,
                     tail: int = 100) -> str:
        """Get logs from all pods of a job."""
        ns = namespace or self.namespace
        pods = self.get_pods(namespace=ns, job_name=job_name)
        
        all_logs = []
        for pod in pods:
            logs = self.get_logs(pod.name, namespace=ns, tail=tail)
            if logs:
                all_logs.append(f"=== Pod: {pod.name} ===\n{logs}")
        
        return '\n\n'.join(all_logs) if all_logs else "No logs available"
    
    def get_namespaces(self) -> List[str]:
        """Get list of namespaces."""
        output = self._run_kubectl(['get', 'namespaces', '-o', 'jsonpath={.items[*].metadata.name}'])
        if output:
            return output.split()
        return ['default']
    
    def delete_resource(self, resource_type: str, name: str, 
                        namespace: Optional[str] = None) -> bool:
        """Delete a resource."""
        ns = namespace or self.namespace
        output = self._run_kubectl([
            'delete', resource_type, name,
            '-n', ns
        ], timeout=60)
        return output is not None
    
    def get_current_namespace(self) -> str:
        """Get the current namespace from kubectl context."""
        output = self._run_kubectl([
            'config', 'view', '--minify', 
            '-o', 'jsonpath={.contexts[0].context.namespace}'
        ])
        return output.strip() if output and output.strip() else 'default'
