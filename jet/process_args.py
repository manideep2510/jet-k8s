import os
import logging
import configparser
from pathlib import Path
import yaml
from .utils import TemplateManager
from .job_config import JobConfig, JobMetadata, JobSpec, PodSpec, ContainerSpec, VolumeSpec, ResourceSpec
from .defaults import *


class ProcessArguments:
    def __init__(self, args):
        self.args = args
        self.template_manager = TemplateManager(templates_dir=JET_HOME / "templates")
        
    def process(self):
        if self.args.jet_command == 'launch':
            if self.args.launch_type == 'job':
                return self._process_launch_job()
            elif self.args.launch_type == 'jupyter':
                return self._process_launch_jupyter()
            elif self.args.launch_type == 'debug':
                return self._process_launch_debug()
        elif self.args.jet_command == 'list':
            if self.args.list_type in ['templates', 'template', 'te', 't']:
                return self._process_list_templates()
            elif self.args.list_type in ['jobs', 'job', 'jo', 'j']:
                return self._process_list_jobs()
            elif self.args.list_type in ['pods', 'pod', 'po', 'p']:
                return self._process_list_pods()
            else:
                return self._process_list_jobs()  # Default to listing jobs
        elif self.args.jet_command == 'get':
            return self._process_get()
        elif self.args.jet_command == 'logs':
            return self._process_logs()
        elif self.args.jet_command == 'describe':
            return self._process_describe()
        elif self.args.jet_command == 'connect':
            return self._process_connect()
        elif self.args.jet_command == 'delete':
            return self._process_delete()
        
    def _process_launch_job(self):

        return self._generate_specs(
            job_type='job',
            backoff_limit=None, # Argument currently not implemented, 6 retries by default
            ttl_seconds_after_finished=DEFAULT_JOB_TTL_SECONDS_AFTER_FINISHED # Argument currently not implemented, defaulted to 15 days   
        )
    
    def _process_launch_jupyter(self):
        
        # Parse jupyter specific volumes, ports, command
        jupyter_volumes = self._parse_volume_arg([[self.args.notebooks_dir]], identifier="jupyter-notebooks")

        # Parse jupyter port argument
        port = self.args.port or DEFAULT_JUPYTER_PORT
        if ':' in port:
            host_port = int(port.split(':')[0])
            jupyter_container_port = int(port.split(':')[1])
        else:
            host_port = int(port)
            jupyter_container_port = int(port)

        jupyter_ports = [{
            'name': 'jupyter',
            'container_port': jupyter_container_port,
            'host_port': host_port
        }]

        # Jupyter command
        if self.args.token:
            jupyter_command = f"jupyter notebook --port={jupyter_container_port} --no-browser --ip=127.0.0.1 --NotebookApp.token={self.args.token}"
        else:
            jupyter_command = f"jupyter notebook --port={jupyter_container_port} --no-browser --ip=127.0.0.1"

        # Set HOME, so that jupyter uses correct home directory inside container to find .local, .jupyter, .ipython
        # Add respective volumes and mounts
        # TODO: Make this optional with a flag to choose the path to mount as jupyter HOME and add volumes?
        jupyter_env_vars = {}
        jupyter_env_vars['HOME'] = os.path.expanduser("~")

        # Add .local, .jupyter, .ipython as volumes
        jupyter_volumes.extend(self._parse_volume_arg([[os.path.join(os.path.expanduser("~"), '.local')], 
                                                      [os.path.join(os.path.expanduser("~"), '.jupyter')], 
                                                      [os.path.join(os.path.expanduser("~"), '.ipython')]], 
                                                      identifier="jupyter-config"))
        
        if self.args.notebooks_dir is None:
            logging.warning("Notebooks directory not provided. It's recommended to provide a notebooks directory using --notebooks-dir/-np flag to persist your notebooks.")

        return self._generate_specs(
            job_type='jupyter',
            backoff_limit=0, # No retries for jupyter jobs
            ttl_seconds_after_finished=DEFAULT_JUPYTER_TTL_SECONDS_AFTER_FINISHED, # Argument currently not implemented, defaulted to 15 days  
            additional_volumes=jupyter_volumes, 
            additional_envs=jupyter_env_vars, 
            additional_ports=jupyter_ports, # Jupyter port inside pod
            command_override=jupyter_command, # Jupyter command to start the notebook
            working_dir_override=self.args.notebooks_dir # Set working dir to notebooks path
        )

    def _process_launch_debug(self):
        
        debug_command = "sleep infinity"
        # Set active deadline seconds to limit the duration of the debug session to the provided duration.
        active_deadline_seconds = self.args.duration if self.args.duration else DEFAULT_DEBUG_JOB_DURATION_SECONDS

        return self._generate_specs(
            job_type='debug',
            backoff_limit=0, # No retries for debug jobs
            ttl_seconds_after_finished=DEFAULT_DEBUG_TTL_SECONDS_AFTER_FINISHED, # 6 hours for debug jobs
            command_override=debug_command,
            active_deadline_seconds=active_deadline_seconds
        )
    
    def _process_list_templates(self):
        job_type = self.args.type if self.args.type else None
        name_match_substr = self.args.name if self.args.name else None
        regex = self.args.regex if self.args.regex else None
        sort_by = self.args.sort_by
        verbose = self.args.verbose if self.args.verbose else False
        return {
            'job_type': job_type,
            'verbose': verbose,
            'name_match_substr': name_match_substr,
            'regex': regex,
            'sort_by': sort_by
        }
    
    def _process_list_jobs(self):
        namespace = self.args.namespace if hasattr(self.args, 'namespace') and self.args.namespace else None
        return {
            'namespace': namespace
        }

    def _process_list_pods(self):
        namespace = self.args.namespace if hasattr(self.args, 'namespace') and self.args.namespace else None
        return {
            'namespace': namespace
        }

    # TODO: Yet to implement
    def _process_get(self):
        pass

    def _process_logs(self):
        """Process logs command arguments.
        
        Supports formats:
        - jet logs <job_name>                       # defaults to job
        - jet logs pod <pod_name>                   # explicitly get pod logs
        - jet logs job <job_name>                   # explicitly get job logs
        - jet logs <job_name> -f                    # with kubectl args
        - jet logs pod <pod_name> --tail=100        # pod with kubectl args
        - jet logs <job_name> -n namespace          # with namespace
        """
        args_list = list(self.args.logs_args) if hasattr(self.args, 'logs_args') else []
        
        # Extract namespace from args if present (-n or --namespace)
        namespace = None
        i = 0
        while i < len(args_list):
            if args_list[i] in ['-n', '--namespace'] and i + 1 < len(args_list):
                namespace = args_list[i + 1]
                args_list.pop(i)  # Remove -n/--namespace
                args_list.pop(i)  # Remove the namespace value
            elif args_list[i].startswith('--namespace='):
                namespace = args_list[i].split('=', 1)[1]
                args_list.pop(i)
            else:
                i += 1
        
        kubectl_args = []
        resource_type = 'job'  # Default to job
        name = None

        if len(args_list) == 0:
            resource_type = None
            name = None
            kubectl_args = []
        elif len(args_list) == 1:
            # jet logs <name> -> default to job
            resource_type = 'job'
            name = args_list[0]
            kubectl_args = []
        else:
            # jet logs <resource_type> <name> [kubectl_args...]
            # or jet logs <name> [kubectl_args...]
            first_arg = args_list[0].lower()
            if first_arg in ['job', 'pod', 'jobs', 'pods', 'jo', 'po', 'j', 'p']:
                # Normalize resource type
                if first_arg in ['pod', 'pods', 'po', 'p']:
                    resource_type = 'pod'
                else:
                    resource_type = 'job'
                # Remaining args after resource_type and name are kubectl args
                kubectl_args = args_list[2:] if len(args_list) > 2 else []
                name = args_list[1]
            else:
                # First arg is not a resource type, treat as job name
                # Remaining args are kubectl args
                kubectl_args = args_list[1:] if len(args_list) > 1 else []
                resource_type = 'job'
                name = args_list[0]
            
        return {
            'resource_type': resource_type,
            'name': name,
            'namespace': namespace,
            'kubectl_args': kubectl_args
        }

    def _process_describe(self):
        """Process describe command arguments.
        
        Supports formats:
        - jet describe job <job_name>                # describe job
        - jet describe pod <pod_name>                # describe pod
        - jet describe job <job_name> -n namespace   # job with namespace
        - jet describe pod <pod_name> -n namespace   # pod with namespace
        
        Note: Resource type (job/pod) is required.
        """
        args_list = list(self.args.describe_args) if hasattr(self.args, 'describe_args') else []
        
        # Extract namespace from args if present (-n or --namespace)
        namespace = None
        i = 0
        while i < len(args_list):
            if args_list[i] in ['-n', '--namespace'] and i + 1 < len(args_list):
                namespace = args_list[i + 1]
                args_list.pop(i)  # Remove -n/--namespace
                args_list.pop(i)  # Remove the namespace value
            elif args_list[i].startswith('--namespace='):
                namespace = args_list[i].split('=', 1)[1]
                args_list.pop(i)
            else:
                i += 1
        
        resource_type = None
        name = None
        kubectl_args = []

        if len(args_list) >= 2:
            # jet describe <resource_type> <name> [kubectl_args...]
            first_arg = args_list[0].lower()
            if first_arg in ['job', 'pod', 'jobs', 'pods', 'jo', 'po', 'j', 'p']:
                # Normalize resource type
                if first_arg in ['pod', 'pods', 'po', 'p']:
                    resource_type = 'pod'
                else:
                    resource_type = 'job'
                name = args_list[1]
                # Remaining args after resource_type and name are kubectl args
                kubectl_args = args_list[2:] if len(args_list) > 2 else []
            
        return {
            'resource_type': resource_type,
            'name': name,
            'namespace': namespace,
            'kubectl_args': kubectl_args
        }

    def _process_connect(self):
        """Process connect command arguments.
        
        Supports formats:
        - jet connect <job_name>                     # defaults to job
        - jet connect pod <pod_name>                 # explicitly connect to pod
        - jet connect job <job_name>                 # explicitly connect to job
        """
        connect_args = self.args.connect_args if hasattr(self.args, 'connect_args') else []
        namespace = self.args.namespace if hasattr(self.args, 'namespace') and self.args.namespace else None
        
        resource_type = 'job'  # Default to job
        name = None
        
        if len(connect_args) >= 1:
            # Check if first argument is a resource type
            if connect_args[0] in ['job', 'pod', 'jobs', 'pods', 'jo', 'po', 'j', 'p']:
                if connect_args[0] in ['pod', 'pods', 'po', 'p']:
                    resource_type = 'pod'
                else:
                    resource_type = 'job'
                if len(connect_args) >= 2:
                    name = connect_args[1]
            else:
                # First argument is the name, default to job
                name = connect_args[0]
        
        return {
            'resource_type': resource_type,
            'name': name,
            'namespace': namespace
        }

    def _process_delete(self):
        """Process delete command arguments.
        
        Supports formats:
        - jet delete <job_name>                      -> defaults to job
        - jet delete pod <pod_name>                  -> explicitly delete pod
        - jet delete job <job_name>                  -> explicitly delete job
        - jet delete <job_name> --force --grace-period=0  -> with kubectl args
        - jet delete pod <pod_name> --force          -> pod with kubectl args
        - jet delete <job_name> -n namespace         -> with namespace
        """
        args_list = list(self.args.delete_args) if hasattr(self.args, 'delete_args') else []
        
        # Extract namespace from args if present (-n or --namespace)
        namespace = None
        i = 0
        while i < len(args_list):
            if args_list[i] in ['-n', '--namespace'] and i + 1 < len(args_list):
                namespace = args_list[i + 1]
                args_list.pop(i)  # Remove -n/--namespace
                args_list.pop(i)  # Remove the namespace value
            elif args_list[i].startswith('--namespace='):
                namespace = args_list[i].split('=', 1)[1]
                args_list.pop(i)
            else:
                i += 1
        
        resource_type = None
        name = None
        kubectl_args = []

        if len(args_list) == 0:
            resource_type = None
            name = None
            kubectl_args = []
        elif len(args_list) == 1:
            # jet delete <name> -> default to job
            resource_type = 'job'
            name = args_list[0]
            kubectl_args = []
        else:
            # jet delete <resource_type> <name> [kubectl_args...]
            # or jet delete <name> [kubectl_args...]
            first_arg = args_list[0].lower()
            if first_arg in ['job', 'pod', 'jobs', 'pods', 'jo', 'po', 'j', 'p']:
                # Normalize resource type
                if first_arg in ['pod', 'pods', 'po', 'p']:
                    resource_type = 'pod'
                else:
                    resource_type = 'job'
                # Remaining args after resource_type and name are kubectl args
                kubectl_args = args_list[2:] if len(args_list) > 2 else []
                name = args_list[1]
            else:
                # First arg is not a resource type, treat as job name
                # Remaining args are kubectl args
                kubectl_args = args_list[1:] if len(args_list) > 1 else []
                resource_type = 'job'
                name = args_list[0]
            
        return {
            'resource_type': resource_type,
            'name': name,
            'namespace': namespace,
            'kubectl_args': kubectl_args
        }

    def _add_volume_with_dedupe(self, pod_spec, volume_dict, existing_by_name, existing_by_mount, dedupe_by_name=False):
        """
        Add a volume to pod_spec while deduplicating by mount_path and optionally by name.
        
        Args:
            pod_spec: PodSpec object to add volume to
            volume_dict: Dictionary with volume details (name, volume_type, details, mount_path)
            existing_by_name: Dictionary tracking volumes by name
            existing_by_mount: Dictionary tracking volumes by mount_path
            dedupe_by_name: If True, also deduplicate by volume name (for auto-generated names).
                           If False, only deduplicate by mount_path (default behavior for CLI volumes).
        """
        new_vol = VolumeSpec(
            name=volume_dict['name'],
            volume_type=volume_dict['volume_type'],
            details=volume_dict['details'],
            mount_path=volume_dict['mount_path']
        )
        
        # Remove conflicting volumes from template
        # Always deduplicate by mount path (can't have two volumes at same mount point)
        if new_vol.mount_path and new_vol.mount_path in existing_by_mount:
            conflicting_vol = existing_by_mount[new_vol.mount_path]
            if conflicting_vol in pod_spec.volumes:
                pod_spec.volumes.remove(conflicting_vol)
                # Also remove from name tracking if it was there
                if conflicting_vol.name in existing_by_name:
                    existing_by_name.pop(conflicting_vol.name)
            existing_by_mount.pop(new_vol.mount_path)
        
        # Optionally deduplicate by name (for auto-generated volume names like pyenv-volume, jupyter-notebooks-0)
        if dedupe_by_name and new_vol.name in existing_by_name:
            conflicting_vol = existing_by_name[new_vol.name]
            if conflicting_vol in pod_spec.volumes:
                pod_spec.volumes.remove(conflicting_vol)
                # Also remove from mount tracking if it was there
                if conflicting_vol.mount_path and conflicting_vol.mount_path in existing_by_mount:
                    existing_by_mount.pop(conflicting_vol.mount_path)
            existing_by_name.pop(new_vol.name)
        
        # Add new volume and update tracking
        pod_spec.volumes.append(new_vol)
        existing_by_name[new_vol.name] = new_vol
        if new_vol.mount_path:
            existing_by_mount[new_vol.mount_path] = new_vol
        
        return new_vol

    def _generate_specs(self, job_type, backoff_limit, ttl_seconds_after_finished, additional_volumes=[], additional_envs={}, additional_ports=[], command_override=None, working_dir_override=None, active_deadline_seconds=None):
        
        # 1. Load Base Config
        if self.args.template:
            template_path = self.template_manager.resolve_template_path(self.args.template, job_type)
            if template_path:
                print(f"Using template file: {template_path} for launching the job")
                job_config = self._load_job_config(template_path)
        elif os.path.isfile(os.path.abspath(self.args.name)):
             logging.info(f"Job file provided: {self.args.name}. Loading job configuration from the file.")
             job_config = self._load_job_config(os.path.abspath(self.args.name))
        else:
            # Create default config
            job_config = JobConfig(
                metadata=JobMetadata(name=self.args.name, labels={'job-type': job_type}),
                spec=JobSpec(
                    template_spec=PodSpec(
                        containers=[ContainerSpec(name='main')]
                    )
                )
            )

        # 2. Apply Overrides (CLI > Base)
        
        # Metadata
        if not os.path.isfile(os.path.abspath(self.args.name)):
             job_config.metadata.name = self.args.name
        
        if self.args.namespace:
            job_config.metadata.namespace = self.args.namespace
        
        # Priority
        # TODO: Create a separate priority class for jupyter and debug jobs. For now, using 'train' priority class.
        priority = self.args.priority if hasattr(self.args, 'priority') and self.args.priority else job_config.metadata.labels.get('priorityClassName', DEFAULT_PRIORITY)
        job_config.metadata.labels['priorityClassName'] = priority
        job_config.metadata.labels['job-type'] = job_type

        # Job Spec
        if backoff_limit is not None:
             job_config.spec.backoff_limit = backoff_limit
        elif job_config.spec.backoff_limit is None:
             # Default if not in template and not passed
             pass 
        
        if ttl_seconds_after_finished is not None:
            job_config.spec.ttl_seconds_after_finished = ttl_seconds_after_finished

        # Pod Spec
        pod_spec = job_config.spec.template_spec
        
        if hasattr(self.args, 'scheduler') and self.args.scheduler:
            pod_spec.scheduler = self.args.scheduler
        elif not pod_spec.scheduler:
            pod_spec.scheduler = DEFAULT_SCHEDULER

        if hasattr(self.args, 'restart_policy') and self.args.restart_policy:
            pod_spec.restart_policy = self.args.restart_policy
        elif not pod_spec.restart_policy:
            pod_spec.restart_policy = DEFAULT_RESTART_POLICY

        if active_deadline_seconds is not None:
            pod_spec.active_deadline_seconds = active_deadline_seconds
        
        # Node Selectors
        if self.args.node_selector:
            cli_selectors = {i.split('=')[0]:i.split('=')[1] for sublist in self.args.node_selector for i in sublist}
            pod_spec.node_selectors.update(cli_selectors)
        
        if hasattr(self.args, 'gpu_type') and self.args.gpu_type:
            pod_spec.node_selectors['gpu-type'] = self.args.gpu_type

        # Volumes - Deduplicate by name and mount_path (CLI args override template)
        # Build a map of existing volumes from template
        existing_volumes_by_name = {vol.name: vol for vol in pod_spec.volumes}
        existing_volumes_by_mount = {vol.mount_path: vol for vol in pod_spec.volumes if vol.mount_path}
        
        if self.args.volume:
            cli_volumes = self._parse_volume_arg(self.args.volume)
            for v in cli_volumes:
                # CLI volumes: only dedupe by mount_path, not by name
                self._add_volume_with_dedupe(pod_spec, v, existing_volumes_by_name, existing_volumes_by_mount, dedupe_by_name=False)

        if self.args.shm_size:
            shm_vol = self._parse_shm_size_arg(self.args.shm_size)
            # shm-volume: dedupe by both name and mount_path (auto-generated name)
            self._add_volume_with_dedupe(pod_spec, shm_vol, existing_volumes_by_name, existing_volumes_by_mount, dedupe_by_name=True)

        # Additional Volumes - Deduplicate by name and mount_path (auto-generated names like jupyter-notebooks-0)
        for v in additional_volumes:
            self._add_volume_with_dedupe(pod_spec, v, existing_volumes_by_name, existing_volumes_by_mount, dedupe_by_name=True)

        # Security Context
        # TODO: Make this optional with a flag? Should allowPrivilegeEscalation and runAsNonRoot be configurable?
        pod_spec.security_context = {
            'runAsUser': os.getuid(),
            'runAsGroup': os.getgid(),
            'fsGroup': os.getgid(),
            'runAsNonRoot': True
        }
        pod_spec.containers[0].security_context = pod_spec.security_context.copy()
        pod_spec.containers[0].security_context['allowPrivilegeEscalation'] = False
        # Remove fsGroup from container security context as it's not valid there
        if 'fsGroup' in pod_spec.containers[0].security_context:
            pod_spec.containers[0].security_context.pop('fsGroup')

        # Container Spec
        if not pod_spec.containers:
            pod_spec.containers.append(ContainerSpec(name='main'))
        container = pod_spec.containers[0]

        if self.args.image:
            container.image = self.args.image
        
        if self.args.image_pull_policy:
            container.image_pull_policy = self.args.image_pull_policy
        
        # Command
        if hasattr(self.args, 'shell') and self.args.shell:
             container.command = self.args.shell + " -c"
        elif not container.command:
             container.command = "/bin/sh -c"

        if command_override:
            container.args = [command_override]
        elif hasattr(self.args, 'command') and self.args.command:
            container.args = [self.args.command]
        
        # Working Dir
        if working_dir_override:
            container.working_dir = working_dir_override
        elif hasattr(self.args, 'working_dir') and self.args.working_dir:
            container.working_dir = self.args.working_dir

        # Env
        if hasattr(self.args, 'env') and self.args.env:
            container.env.update(self._parse_env_arg(self.args.env))
        container.env.update(additional_envs)

        # Volume Mounts
        # Update mounts from new volumes
        for vol in pod_spec.volumes:
            if vol.mount_path:
                container.volume_mounts[vol.name] = vol.mount_path

        # Resources
        if self.args.cpu:
            req, lim = self.args.cpu.split(':') if ':' in self.args.cpu else (self.args.cpu, self.args.cpu)
            container.resources.cpu_request = req
            container.resources.cpu_limit = lim
        elif not container.resources.cpu_request:
             container.resources.cpu_request = DEFAULT_CPU.split(':')[0]
             container.resources.cpu_limit = DEFAULT_CPU.split(':')[1]

        if self.args.memory:
            req, lim = self.args.memory.split(':') if ':' in self.args.memory else (self.args.memory, self.args.memory)
            container.resources.memory_request = req
            container.resources.memory_limit = lim
        elif not container.resources.memory_request:
             container.resources.memory_request = DEFAULT_MEMORY.split(':')[0]
             container.resources.memory_limit = DEFAULT_MEMORY.split(':')[1]

        if hasattr(self.args, 'gpu') and self.args.gpu:
            container.resources.gpu_count = int(self.args.gpu)
        
        if hasattr(self.args, 'gpu_type') and self.args.gpu_type:
            container.resources.gpu_type = self.args.gpu_type

        # Pyenv - Deduplicate volumes (auto-generated names: pyenv-volume, uv-base-volume)
        if hasattr(self.args, 'pyenv') and self.args.pyenv:
            pyenv_volumes, pyenv_env_vars = self._parse_pyenv_arg(self.args.pyenv)
            for v in pyenv_volumes:
                new_vol = self._add_volume_with_dedupe(pod_spec, v, existing_volumes_by_name, existing_volumes_by_mount, dedupe_by_name=True)
                container.volume_mounts[new_vol.name] = new_vol.mount_path
            container.env.update(pyenv_env_vars)

        # Mount Home - Deduplicate volumes (auto-generated name: home-0)
        if self.args.mount_home:
            home_path = os.path.expanduser("~")
            home_volumes = self._parse_volume_arg([[home_path]], identifier="home")
            for v in home_volumes:
                new_vol = self._add_volume_with_dedupe(pod_spec, v, existing_volumes_by_name, existing_volumes_by_mount, dedupe_by_name=True)
                container.volume_mounts[new_vol.name] = new_vol.mount_path
            container.env['HOME'] = home_path
            if not container.working_dir:
                container.working_dir = home_path
            if not container.working_dir:
                container.working_dir = home_path

        # Ports - Deduplicate by name (additional_ports override existing)
        # TODO: Handling additional ports from outside, need to handle ports in general and implement port inputs from args (for forwarding in normal jobs)
        existing_ports_by_name = {port['name']: port for port in job_config.ports if isinstance(port, dict) and 'name' in port}
        for port in additional_ports:
            if isinstance(port, dict) and 'name' in port:
                # Remove conflicting port from template
                if port['name'] in existing_ports_by_name:
                    job_config.ports.remove(existing_ports_by_name[port['name']])
                    existing_ports_by_name.pop(port['name'])
                job_config.ports.append(port)
                existing_ports_by_name[port['name']] = port
            else:
                # Port without name, just append
                job_config.ports.append(port)
        
        # Flags
        job_config.follow = self.args.follow if hasattr(self.args, 'follow') else False
        job_config.dry_run = self.args.dry_run if hasattr(self.args, 'dry_run') else False
        job_config.verbose = self.args.verbose if hasattr(self.args, 'verbose') else False
        job_config.save_template = self.args.save_template if hasattr(self.args, 'save_template') else False

        return job_config


    def _parse_shm_size_arg(self, shm_size):
        volume_name = 'shm-volume'
        mount_path = '/dev/shm'
        volume_type = 'emptyDir'
        volume_details = {'name': volume_name, 'volume_type': volume_type, 'mount_path': mount_path, 'details': {'sizeLimit': shm_size}}
        return volume_details

    def _parse_volume_arg(self, volume_args, identifier="volume"):
        volumes = []
        count = 0
        for vol_list in volume_args:
            for vol in vol_list:
                # Skip None values
                if vol is None:
                    continue
                # Parse volume string
                vol_split = vol.split(':')
                if len(vol_split) == 1:
                    volume_name = f"{identifier}-{count}"
                    host_path = vol_split[0]
                    mount_path = vol_split[0]
                    volume_type = 'Directory'
                    volume_details = {'name': volume_name, 'volume_type': 'hostPath', 'mount_path': mount_path, 'details': {'path': host_path, 'type': volume_type}}
                    volumes.append(volume_details)
                elif len(vol_split) == 2:
                    volume_name = f"{identifier}-{count}"
                    host_path = vol_split[0]
                    mount_path = vol_split[1]
                    volume_type = 'Directory'
                    volume_details = {'name': volume_name, 'volume_type': 'hostPath', 'mount_path': mount_path, 'details': {'path': host_path, 'type': volume_type}}
                    volumes.append(volume_details)
                elif len(vol_split) == 4:
                    volume_name = vol_split[0]
                    host_path = vol_split[1]
                    mount_path = vol_split[2]
                    volume_type = vol_split[3]
                    if volume_type == 'emptyDir':
                        raise ValueError("emptyDir volume type not supported. Use --shm-size flag to set /dev/shm size inside the container if needed.")
                    if volume_type not in ['Directory', 'File', 'DirectoryOrCreate', 'FileOrCreate']: # emptyDir not supported via volume mount through CLI
                        raise ValueError("Volume type not supported. Accepted types are: Directory, File, DirectoryOrCreate, FileOrCreate")
                    else:
                        volume_details = {'name': volume_name, 'volume_type': 'hostPath', 'mount_path': mount_path, 'details': {'path': host_path, 'type': volume_type}}
                        volumes.append(volume_details)
                else:
                    raise ValueError("Invalid volume format. Accepted volume formats are: host_path or host_path:mount_path or volume_name:host_path:mount_path:Type")
                count += 1
        return volumes

    def _parse_env_arg(self, env_args):
        env_vars = {}
        for env_list in env_args:
            for env in env_list:
                if os.path.isfile(env):
                    # Read env file and parse key=value pairs
                    with open(env, 'r') as f:
                        for line in f:
                            line = line.strip()
                            if line and '=' in line:
                                key, value = line.split('=', 1)
                                env_vars[key] = value
                elif '=' in env:
                    key, value = env.split('=', 1)
                    env_vars[key] = value
                else:
                    raise ValueError("Invalid environment variable format. Use KEY=VALUE or provide a valid env file path.")
        return env_vars
    
    def _parse_pyenv_arg(self, pyenv_arg):
        """
        Mount the provided pyenv path to the same path inside the container
        If conda env is provided, set CONDA_PREFIX env variable to the pyenv path. Python executable is automatically picked from conda env.
        If venv or uv env is provided, set VIRTUAL_ENV env variable to the pyenv path. Python executable base path is automatically picked 
        from uv/venv env pyvenv.cfg and mounted as a volume. 
        Set PATH env variable to include the pyenv bin directory
        """
        pyenv_volume_details = []

        volume_name = 'pyenv-volume'
        host_path = pyenv_arg
        mount_path = pyenv_arg
        volume_type = 'Directory'
        pyenv_volume_details.append({'name': volume_name, 'volume_type': 'hostPath', 'mount_path': mount_path, 'details': {'path': host_path, 'type': volume_type}})

        # Env vars and additional volume for uv base path if detected
        files_in_pyenv = os.listdir(pyenv_arg)
        pyenv_env_vars = {}
        if 'conda-meta' in files_in_pyenv:
            pyenv_env_vars = {'CONDA_PREFIX': pyenv_arg}
            pyenv_env_vars = {'PATH': f"{pyenv_arg}/bin:/usr/local/cuda/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"}
            
        elif 'pyvenv.cfg' in files_in_pyenv:
            # Read pyvenv.cfg to get python excecutable base path for mounting
            with open(os.path.join(pyenv_arg, 'pyvenv.cfg'), 'r') as f:
                pyvenv = f.read()

            config_parser = configparser.ConfigParser()
            config_parser.read_string("[header]\n" + pyvenv)
            try:
                home_path = config_parser["header"]["home"]
            except KeyError:
                logging.warning("Invalid pyvenv.cfg format for uv or venv env. 'home' key not found.")
                home_path = None
            python_base = str(Path(home_path).parents[0]) if home_path else None
            pyenv_volume_details.append({'name': 'uv-base-volume', 'volume_type': 'hostPath',
                                        'mount_path': python_base, "read_only": True, 
                                        'details': {'path': python_base, 'type': 'Directory'}})

            pyenv_env_vars = {'VIRTUAL_ENV': pyenv_arg}
            pyenv_env_vars = {'PATH': f"{pyenv_arg}/bin:/usr/local/cuda/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"}

            # Unset PYTHONHOME to avoid conflicts
            pyenv_env_vars.update({'PYTHONHOME': ''})

        else:
            raise ValueError("Unsupported pyenv type. Supported envs are: conda, venv, uv, poetry, etc. detected by presence of conda-meta or pyvenv.cfg in the provided path.")

        # Set PS1 to indicate pyenv is active in the container shell
        # ps1 = f"({os.path.basename(pyenv_arg)}) \\u@\\h:\\w$ "
        # pyenv_env_vars.update({'PS1': ps1})
        # pyenv_env_vars.update({'PROMPT_COMMAND': f'export PS1="{ps1}"'}) 
        # pyenv_env_vars.update({'PYTHONUNBUFFERED': '1'}) # To ensure python output is unbuffered in logs
        
        return pyenv_volume_details, pyenv_env_vars

    def _load_job_config(self, path):
        with open(path, 'r') as f:
            data = yaml.safe_load(f)
        return JobConfig.from_dict(data)