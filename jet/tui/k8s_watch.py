"""Async Kubernetes client using kr8s for watch-based updates."""
import asyncio
import time
from datetime import datetime, timezone
from typing import Optional, List, Dict, AsyncGenerator
import kr8s
from kr8s.asyncio.objects import Job, Pod

from .k8s import JobInfo, PodInfo, format_age, format_duration, parse_datetime
from ..utils import get_current_namespace


class Kr8sWatcher:
    """Kubernetes watcher using kr8s for real-time updates.
    
    This class provides async generators that yield updates, designed to work
    with Textual's async worker system.
    """
    
    def __init__(self, namespace: Optional[str] = None):
        self.namespace = namespace or get_current_namespace()
        self._api: Optional[kr8s.asyncio.Api] = None
    
    async def _get_api(self) -> kr8s.asyncio.Api:
        """Get or create the kr8s API client."""
        if self._api is None:
            self._api = await kr8s.asyncio.api()
        return self._api
    
    def _job_from_kr8s(self, job: Job) -> JobInfo:
        """Convert kr8s Job to JobInfo."""
        metadata = job.raw.get('metadata', {})
        status = job.raw.get('status', {})
        spec = job.raw.get('spec', {})
        
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
        
        return JobInfo(
            name=name,
            namespace=self.namespace,
            completions=completions_str,
            duration=duration,
            age=format_age(created_at),
            created_at=created_at,
            status=job_status,
            labels=metadata.get('labels', {}),
            active=active,
            succeeded=succeeded,
            failed=failed,
            start_time=start_time,
            completion_time=completion_time
        )
    
    def _pod_from_kr8s(self, pod: Pod, job_name: Optional[str] = None) -> PodInfo:
        """Convert kr8s Pod to PodInfo."""
        metadata = pod.raw.get('metadata', {})
        status = pod.raw.get('status', {})
        spec = pod.raw.get('spec', {})
        
        name = metadata.get('name', '')
        created_str = metadata.get('creationTimestamp', '')
        created_at = parse_datetime(created_str) or datetime.now(timezone.utc)
        
        # Check if pod is terminating
        is_terminating = metadata.get('deletionTimestamp') is not None
        
        # Ready status
        container_statuses = status.get('containerStatuses', [])
        ready_count = sum(1 for cs in container_statuses if cs.get('ready', False))
        total_containers = len(container_statuses) or len(spec.get('containers', []))
        ready_str = f"{ready_count}/{total_containers}"
        
        # Pod status
        phase = status.get('phase', 'Unknown')
        pod_status = phase
        
        if is_terminating:
            pod_status = "Terminating"
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
        
        # Restarts
        restarts = sum(cs.get('restartCount', 0) for cs in container_statuses)
        
        # Get job name from labels
        labels = metadata.get('labels', {})
        pod_job_name = job_name or labels.get('job-name')
        
        return PodInfo(
            name=name,
            namespace=self.namespace,
            ready=ready_str,
            status=pod_status,
            restarts=restarts,
            cpu='0',
            cpu_percent_request='0',
            cpu_percent_limit='0',
            memory='0',
            memory_percent_request='0',
            memory_percent_limit='0',
            ip=status.get('podIP', '<none>') or '<none>',
            node=spec.get('nodeName', '<none>') or '<none>',
            age=format_age(created_at),
            created_at=created_at,
            labels=labels,
            port_forward=False,
            job_name=pod_job_name
        )
    
    async def watch_jobs(self) -> AsyncGenerator[List[JobInfo], None]:
        """Watch jobs and yield full list on each change.
        
        Does an immediate list fetch first for fast display, then watches for updates.
        This is designed to be used with Textual's run_worker.
        """
        jobs_dict: Dict[str, Job] = {}  # Store raw Job objects
        
        try:
            api = await self._get_api()
            
            # Fast initial fetch using Job.list() - much faster than kr8s.asyncio.get()
            async for job in Job.list(namespace=self.namespace):
                metadata = job.raw.get('metadata', {})
                job_name = metadata.get('name', '')
                jobs_dict[job_name] = job
            
            # Yield immediately with initial data
            yield self._jobs_from_dict(jobs_dict)
            
            # Now watch for changes
            async for event, job in kr8s.asyncio.watch("jobs", namespace=self.namespace):
                metadata = job.raw.get('metadata', {})
                job_name = metadata.get('name', '')
                
                if event in ("ADDED", "MODIFIED"):
                    jobs_dict[job_name] = job
                elif event == "DELETED":
                    jobs_dict.pop(job_name, None)
                
                # Yield on every change
                yield self._jobs_from_dict(jobs_dict)
                
        except asyncio.CancelledError:
            raise
        except Exception:
            # On error, yield current state
            if jobs_dict:
                yield self._jobs_from_dict(jobs_dict)
    
    def _jobs_from_dict(self, jobs_dict: Dict[str, Job]) -> List[JobInfo]:
        """Convert raw Job dict to sorted JobInfo list with fresh ages."""
        jobs = [self._job_from_kr8s(job) for job in jobs_dict.values()]
        return sorted(jobs, key=lambda j: j.created_at, reverse=True)
    
    async def watch_pods(self, job_name: Optional[str] = None) -> AsyncGenerator[List[PodInfo], None]:
        """Watch pods and yield full list on each change.
        
        Does an immediate list fetch first for fast display, then watches for updates.
        This is designed to be used with Textual's run_worker.
        """
        pods_dict: Dict[str, Pod] = {}  # Store raw Pod objects
        
        try:
            api = await self._get_api()
            
            # Build label selector
            label_selector = f"job-name={job_name}" if job_name else None
            
            # Build kwargs for list and watch
            kwargs: Dict = {"namespace": self.namespace}
            if label_selector:
                kwargs["label_selector"] = label_selector
            
            # Fast initial fetch using Pod.list() - much faster than kr8s.asyncio.get()
            async for pod in Pod.list(**kwargs):
                metadata = pod.raw.get('metadata', {})
                pod_name = metadata.get('name', '')
                pods_dict[pod_name] = pod
            
            # Yield immediately with initial data
            yield self._pods_from_dict(pods_dict, job_name)
            
            # Now watch for changes
            async for event, pod in kr8s.asyncio.watch("pods", **kwargs):
                metadata = pod.raw.get('metadata', {})
                pod_name = metadata.get('name', '')
                
                if event in ("ADDED", "MODIFIED"):
                    pods_dict[pod_name] = pod
                elif event == "DELETED":
                    pods_dict.pop(pod_name, None)
                
                # Yield on every change
                yield self._pods_from_dict(pods_dict, job_name)
                
        except asyncio.CancelledError:
            raise
        except Exception:
            # On error, yield current state
            if pods_dict:
                yield self._pods_from_dict(pods_dict, job_name)
    
    def _pods_from_dict(self, pods_dict: Dict[str, Pod], job_name: Optional[str] = None) -> List[PodInfo]:
        """Convert raw Pod dict to sorted PodInfo list with fresh ages."""
        pods = [self._pod_from_kr8s(pod, job_name) for pod in pods_dict.values()]
        return sorted(pods, key=lambda p: p.created_at, reverse=True)
