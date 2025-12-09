from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Any
import yaml
import logging

@dataclass
class ResourceSpec:
    cpu_request: Optional[str] = None
    cpu_limit: Optional[str] = None
    memory_request: Optional[str] = None
    memory_limit: Optional[str] = None
    gpu_count: Optional[int] = None
    gpu_type: Optional[str] = None
    gpu_vendor: str = 'nvidia'

    def validate(self):
        # GPU Count validation
        if self.gpu_count is not None:
            if float(self.gpu_count) <= 0:
                raise ValueError("'gpu_count' must be a positive integer.")
            if float(self.gpu_count) != int(self.gpu_count):
                raise ValueError("'gpu_count' must be an integer value.")

    def get_formatted_vendor(self):
        vendor_map = {
            'nvidia': 'nvidia.com',
            'amd': 'amd.com',
        }
        vendor = self.gpu_vendor.lower()
        if vendor in vendor_map:
            return vendor_map[vendor]
        elif not vendor.endswith('.com'):
             logging.warning(f"Unknown GPU vendor '{vendor}', defaulting to nvidia.com")
             return 'nvidia.com'
        return vendor

@dataclass
class VolumeSpec:
    name: str
    volume_type: str  # 'hostPath', 'emptyDir', etc.
    details: Dict[str, Any]
    mount_path: Optional[str] = None
    read_only: bool = False

# TODO: Support waiting for a different job/pod's completeion to schedule this pod using *init container* or mutating webhook
@dataclass
class ContainerSpec:
    name: str
    image: Optional[str] = None
    image_pull_policy: Optional[str] = None
    command: Optional[str] = None
    args: Optional[List[str]] = None
    env: Dict[str, str] = field(default_factory=dict)
    working_dir: Optional[str] = None
    volume_mounts: Dict[str, str] = field(default_factory=dict)
    resources: ResourceSpec = field(default_factory=ResourceSpec)
    security_context: Dict[str, Any] = field(default_factory=dict)
    is_init_container: bool = False

    def validate(self):
        if self.image_pull_policy is None and self.image and ( self.image.endswith(':latest') or ':' not in self.image):
             logging.warning(f"Image pull policy not set for container {self.name}. Always pulls the image, if it uses 'latest' tag or no tag.")
        self.resources.validate()

@dataclass
class PodSpec:
    scheduler: Optional[str] = None
    priority_class_name: Optional[str] = None  # Standard K8s priority class
    restart_policy: str = 'Never'
    node_selectors: Dict[str, str] = field(default_factory=dict)
    active_deadline_seconds: Optional[int] = None
    volumes: List[VolumeSpec] = field(default_factory=list)
    containers: List[ContainerSpec] = field(default_factory=list)
    security_context: Dict[str, Any] = field(default_factory=dict)

    def validate(self):
        valid_policies = ['Always', 'OnFailure', 'Never']
        if self.restart_policy not in valid_policies:
            raise ValueError(f"'restart_policy' must be one of {valid_policies}")
        
        if not self.containers:
             pass # Warning handled elsewhere or acceptable for partial configs
        
        for container in self.containers:
            container.validate()


# TODO: completions, parallelism, completionMode, backoffLimitPerIndex, activeDeadlineSeconds, podFailurePolicy
# TODO: suspend (pause/resume the job), Others: podReplacementPolicy, manualSelector, selector, templateGeneration, revisionHistoryLimit, successPolicy
@dataclass
class JobSpec:
    backoff_limit: Optional[int] = None
    ttl_seconds_after_finished: Optional[int] = None
    template_spec: PodSpec = field(default_factory=PodSpec)

    def validate(self):
        if self.backoff_limit is not None and self.backoff_limit < 0:
            raise ValueError("'backoff_limit' must be >= 0")
        self.template_spec.validate()

@dataclass
class JobMetadata:
    name: str
    namespace: Optional[str] = None
    labels: Dict[str, str] = field(default_factory=dict)
    annotations: Dict[str, str] = field(default_factory=dict)

@dataclass
class JobConfig:
    metadata: JobMetadata
    spec: JobSpec
    
    # Extra fields for CLI control
    ports: List[Dict[str, Any]] = field(default_factory=list)
    follow: bool = False
    dry_run: bool = False
    verbose: bool = False
    save_template: bool = False

    def validate(self):
        self.spec.validate()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'JobConfig':
        # Parse Metadata
        meta_data = data.get('metadata', {})
        metadata = JobMetadata(
            name=meta_data.get('name', 'unknown'),
            namespace=meta_data.get('namespace'),
            labels=meta_data.get('labels', {}),
            annotations=meta_data.get('annotations', {})
        )

        # Parse Spec
        spec_data = data.get('spec', {})
        template_spec_data = spec_data.get('template', {}).get('spec', {})

        # Parse Volumes
        volumes = []
        for vol in template_spec_data.get('volumes', []):
            if 'hostPath' in vol:
                vol_type = 'hostPath'
                details = vol['hostPath']
            elif 'emptyDir' in vol:
                vol_type = 'emptyDir'
                details = vol['emptyDir']
            else:
                vol_type = 'unknown'
                details = {k: v for k, v in vol.items() if k != 'name'}
            
            volumes.append(VolumeSpec(
                name=vol['name'],
                volume_type=vol_type,
                details=details
            ))

        # Parse Containers
        containers = []
        for cont in template_spec_data.get('containers', []):
            # Resources
            res_data = cont.get('resources', {})
            reqs = res_data.get('requests', {})
            lims = res_data.get('limits', {})
            
            gpu_count = None
            gpu_vendor = 'nvidia' # Default
            for k, v in lims.items():
                if k.endswith('/gpu'):
                    gpu_count = int(v)
                    gpu_vendor = k.split('/')[0]
                    break
            
            resources = ResourceSpec(
                cpu_request=reqs.get('cpu'),
                cpu_limit=lims.get('cpu'),
                memory_request=reqs.get('memory'),
                memory_limit=lims.get('memory'),
                gpu_count=gpu_count,
                gpu_type=template_spec_data.get('nodeSelector', {}).get('gpu-type'), # Inferred from node selector
                gpu_vendor=gpu_vendor
            )

            # Env
            env = {e['name']: str(e['value']) for e in cont.get('env', [])}

            # Volume Mounts
            vol_mounts = {vm['name']: vm['mountPath'] for vm in cont.get('volumeMounts', [])}
            
            # Update mount_path in volumes
            for v in volumes:
                if v.name in vol_mounts:
                    v.mount_path = vol_mounts[v.name]

            containers.append(ContainerSpec(
                name=cont['name'],
                image=cont['image'],
                image_pull_policy=cont.get('imagePullPolicy'),
                command=" ".join(cont['command']) if cont.get('command') else None,
                args=cont.get('args'),
                env=env,
                working_dir=cont.get('workingDir'),
                volume_mounts=vol_mounts,
                security_context=cont.get('securityContext', {}),
                resources=resources
            ))

        pod_spec = PodSpec(
            scheduler=template_spec_data.get('schedulerName'),
            priority_class_name=template_spec_data.get('priorityClassName'),
            restart_policy=template_spec_data.get('restartPolicy', 'Never'),
            node_selectors=template_spec_data.get('nodeSelector', {}),
            active_deadline_seconds=template_spec_data.get('activeDeadlineSeconds'),
            volumes=volumes,
            containers=containers,
            security_context=template_spec_data.get('securityContext', {})
        )

        job_spec = JobSpec(
            backoff_limit=spec_data.get('backoffLimit'),
            ttl_seconds_after_finished=spec_data.get('ttlSecondsAfterFinished'),
            template_spec=pod_spec
        )

        return cls(metadata=metadata, spec=job_spec)

    def to_dict(self) -> Dict[str, Any]:
        # Validate before converting
        self.validate()

        # Convert back to K8s YAML structure
        
        # Containers
        k8s_containers = []
        for cont in self.spec.template_spec.containers:
            c_dict = {
                'name': cont.name,
                'image': cont.image,
            }
            if cont.image_pull_policy:
                c_dict['imagePullPolicy'] = cont.image_pull_policy
            if cont.command:
                c_dict['command'] = cont.command.split() if isinstance(cont.command, str) else cont.command
            if cont.args:
                c_dict['args'] = cont.args
            if cont.working_dir:
                c_dict['workingDir'] = cont.working_dir
            if cont.env:
                c_dict['env'] = [{'name': k, 'value': str(v)} for k, v in cont.env.items()]
            if cont.volume_mounts:
                c_dict['volumeMounts'] = [{'name': k, 'mountPath': v} for k, v in cont.volume_mounts.items()]
            if cont.security_context:
                c_dict['securityContext'] = cont.security_context
            
            # Resources
            res_dict = {}
            reqs = {}
            lims = {}
            if cont.resources.cpu_request: reqs['cpu'] = cont.resources.cpu_request
            if cont.resources.memory_request: reqs['memory'] = cont.resources.memory_request
            if cont.resources.cpu_limit: lims['cpu'] = cont.resources.cpu_limit
            if cont.resources.memory_limit: lims['memory'] = cont.resources.memory_limit
            
            if cont.resources.gpu_count:
                formatted_vendor = cont.resources.get_formatted_vendor()
                lims[f"{formatted_vendor}/gpu"] = str(cont.resources.gpu_count)
            
            if reqs: res_dict['requests'] = reqs
            if lims: res_dict['limits'] = lims
            if res_dict: c_dict['resources'] = res_dict

            k8s_containers.append(c_dict)

        # Volumes
        k8s_volumes = []
        for vol in self.spec.template_spec.volumes:
            v_dict = {'name': vol.name}
            if vol.volume_type == 'hostPath':
                v_dict['hostPath'] = vol.details
            elif vol.volume_type == 'emptyDir':
                v_dict['emptyDir'] = vol.details
            else:
                v_dict.update(vol.details)
            k8s_volumes.append(v_dict)

        # Pod Spec - Build in standard K8s order
        pod_spec_dict = {}
        if self.spec.template_spec.scheduler:
            pod_spec_dict['schedulerName'] = self.spec.template_spec.scheduler
        if self.spec.template_spec.priority_class_name:
            pod_spec_dict['priorityClassName'] = self.spec.template_spec.priority_class_name
        pod_spec_dict['restartPolicy'] = self.spec.template_spec.restart_policy
        if self.spec.template_spec.node_selectors:
            pod_spec_dict['nodeSelector'] = self.spec.template_spec.node_selectors
        if self.spec.template_spec.active_deadline_seconds:
            pod_spec_dict['activeDeadlineSeconds'] = self.spec.template_spec.active_deadline_seconds
        if self.spec.template_spec.security_context:
            pod_spec_dict['securityContext'] = self.spec.template_spec.security_context
        if k8s_volumes:
            pod_spec_dict['volumes'] = k8s_volumes
        pod_spec_dict['containers'] = k8s_containers

        # Job Spec
        job_spec_dict = {}
        if self.spec.backoff_limit is not None:
            job_spec_dict['backoffLimit'] = self.spec.backoff_limit
        if self.spec.ttl_seconds_after_finished is not None:
            job_spec_dict['ttlSecondsAfterFinished'] = self.spec.ttl_seconds_after_finished
        job_spec_dict['template'] = {'spec': pod_spec_dict}

        # Metadata
        metadata_dict = {'name': self.metadata.name}
        if self.metadata.namespace:
            metadata_dict['namespace'] = self.metadata.namespace
        if self.metadata.labels:
            metadata_dict['labels'] = self.metadata.labels
        if self.metadata.annotations:
            metadata_dict['annotations'] = self.metadata.annotations

        return {
            'apiVersion': 'batch/v1',
            'kind': 'Job',
            'metadata': metadata_dict,
            'spec': job_spec_dict
        }
