import os
import logging
import configparser
from pathlib import Path
from .utils import TemplateManager

class ProcessArguments:
    def __init__(self, args):
        self.args = args
        self.template_manager = TemplateManager()
        
    def process(self):
        if self.args.jet_command == 'launch':
            if self.args.launch_type == 'job':
                return self._process_launch_job()
            elif self.args.launch_type == 'jupyter':
                return self._process_launch_jupyter()
            elif self.args.launch_type == 'debug':
                return self._process_launch_debug()
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
            ttl_seconds_after_finished=1296000 # Argument currently not implemented, defaulted to 15 days   
        )
    
    def _process_launch_jupyter(self):
        
        # Parse jupyter specific volumes, ports, command
        jupyter_volumes = self._parse_volume_arg([[self.args.notebooks_dir]], identifier="jupyter-notebooks")

        # Parse jupyter port argument
        if ':' in self.args.port:
            host_port = int(self.args.port.split(':')[0])
            jupyter_container_port = int(self.args.port.split(':')[1])
        else:
            host_port = int(self.args.port)
            jupyter_container_port = int(self.args.port)

        jupyter_ports = [{
            'name': 'jupyter',
            'container_port': jupyter_container_port,
            'host_port': host_port
        }]

        # Jupyter command
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
            ttl_seconds_after_finished=1296000, # Argument currently not implemented, defaulted to 15 days  
            additional_volumes=jupyter_volumes, 
            additional_envs=jupyter_env_vars, 
            additional_ports=jupyter_ports, # Jupyter port inside pod
            command_override=jupyter_command, # Jupyter command to start the notebook
            working_dir_override=self.args.notebooks_dir # Set working dir to notebooks path
        )

    def _process_launch_debug(self):
        
        debug_command = "sleep infinity"
        # Set active deadline seconds to limit the duration of the debug session to the provided duration.
        active_deadline_seconds = self.args.duration

        return self._generate_specs(
            job_type='debug',
            backoff_limit=0, # No retries for debug jobs
            ttl_seconds_after_finished=21600, # 6 hours for debug jobs
            command_override=debug_command,
            active_deadline_seconds=active_deadline_seconds
        )

    # TODO: Yet to implement
    def _process_get(self):
        pass

    # TODO: Yet to implement
    def _process_logs(self):
        pass

    # TODO: Yet to implement
    def _process_describe(self):
        pass

    # TODO: Yet to implement
    def _process_connect(self):
        pass

    # TODO: Yet to implement
    def _process_delete(self):
        pass

    def _generate_specs(self, job_type, backoff_limit, ttl_seconds_after_finished, additional_volumes=[], additional_envs={}, additional_ports=[], command_override=None, working_dir_override=None, active_deadline_seconds=None):
        
        if self.args.template:
            template_path = self.template_manager.resolve_template_path(self.args.template, job_type)
            if template_path:
                print(f"Using template file: {template_path} for launching the job.")
            # return str(template_path)
            # TODO: Merging template specs with CLI args instead of returning template path directly, i.e, override template specs with CLI args.
            return str(template_path)
        
        # If args.name is a file path, return it as is.
        if os.path.isfile(os.path.abspath(self.args.name)):
            logging.info(f"Job file provided: {self.args.name}. Ignoring other launch job arguments.")
            return os.path.abspath(self.args.name)
        
        # Process job details arguments
        job_details_args = {
            'job_name': self.args.name,
            'namespace': self.args.namespace,
            # TODO: Create a separate priority class for jupyter and debug jobs. For now, using 'train' priority class.
            'labels': {'priorityClassName': self.args.priority if hasattr(self.args, 'priority') else 'train',
                       'job-type': job_type
                       },
            'annotations': None,
        }

        # Process job spec arguments
        job_spec_args = {
            'backoff_limit': backoff_limit,
            'ttl_seconds_after_finished': ttl_seconds_after_finished
        }

        # Process pod spec arguments
        pod_spec_args = {
            'scheduler': self.args.scheduler,
            'restart_policy': self.args.restart_policy if hasattr(self.args, 'restart_policy') else 'Never',
            'num_restarts': None, # A custom pod level number of restarts. Argument currently not implemented, unlimited pod restarts
            'node_selectors': {i.split('=')[0]:i.split('=')[1] for sublist in self.args.node_selector for i in sublist} if self.args.node_selector else {},
            'activeDeadlineSeconds': active_deadline_seconds,
            'volumes': []
        }

        # Pass GPU type as node selector
        if hasattr(self.args, 'gpu_type') and self.args.gpu_type:
            # pod_spec_args['node_selectors']['nvidia.com/gpu.product'] = self.args.gpu_type
            pod_spec_args['node_selectors']['gpu-type'] = self.args.gpu_type

        # Parse volume arguments
        if self.args.volume:
            volumes = self._parse_volume_arg(self.args.volume)
            pod_spec_args['volumes'] = volumes

        # Process shm-size as emptyDir volume mount to /dev/shm
        if self.args.shm_size:
            shm_volume = self._parse_shm_size_arg(self.args.shm_size)
            pod_spec_args['volumes'].append(shm_volume)

        # TODO: Handle ports in general
        # Format of ports: [{'name': 'port-name', 'container_port': 8888, 'host_port': 8888}, ...]
        ports = []
        # Parse ports from args (currently not implemented for non-jupyter jobs)

        # Handle ports for custom jobs using additional_ports argument
        # For jupyter jobs, this will be the a port named 'jupyter'
        ports.extend(additional_ports)

        # Add Security Context to pod spec to pass the user
        # TODO: Make this optional with a flag?
        pod_spec_args['securityContext'] = {
            'runAsUser': os.getuid(),
            'runAsGroup': os.getgid(),
            'fsGroup': os.getgid()
        }

        # Process container spec arguments
        container_spec_args = {
            'name': 'main',
            'image': self.args.image,
            'image_pull_policy': self.args.image_pull_policy,
            'command': self.args.shell + " -c" if hasattr(self.args, 'shell') and self.args.shell else "/bin/sh -c",
            'args': command_override if command_override else (self.args.command if hasattr(self.args, 'command') else ""),
            'env': {}, # To be filled from args.env
            'workingDir': working_dir_override if working_dir_override else (self.args.working_dir if hasattr(self.args, 'working_dir') else None),
            'volume_mounts': {}, # To be filled from pod_spec_args volumes
            'resources': {
                'cpu_request': self.args.cpu.split(':')[0],
                'cpu_limit': self.args.cpu.split(':')[1] if ':' in self.args.cpu else self.args.cpu.split(':')[0],
                'memory_request': self.args.memory.split(':')[0],
                'memory_limit': self.args.memory.split(':')[1] if ':' in self.args.memory else self.args.memory.split(':')[0],
                'gpu_count': self.args.gpu if hasattr(self.args, 'gpu') else None,
                'gpu_type': self.args.gpu_type if hasattr(self.args, 'gpu_type') else None,
                #'gpu_memory': self.args.gpu_memory, # Argument currently not implemented
                'gpu_vendor': 'nvidia' # Currently only nvidia GPUs are supported
            },
            'is_initContainer': False
        }

        # Process pyenv argument
        if hasattr(self.args, 'pyenv') and self.args.pyenv:
            pyenv_volumes, pyenv_env_vars = self._parse_pyenv_arg(self.args.pyenv)
            pod_spec_args['volumes'].extend(pyenv_volumes)
            container_spec_args['env'].update(pyenv_env_vars)

        # Handle additional environment variables for custom jobs
        container_spec_args['env'].update(additional_envs)

        # Handle additional volume inputs for custom jobs such as HOME and jupyter config volumes for jupyter jobs
        pod_spec_args['volumes'].extend(additional_volumes)

        # Mount home and set HOME env var if --mount-home flag is provided
        if self.args.mount_home:
            home_path = os.path.expanduser("~")
            home_volumes = self._parse_volume_arg([[home_path]], identifier="home")
            pod_spec_args['volumes'].extend(home_volumes)

            # Env var for HOME
            container_spec_args['env']['HOME'] = home_path

            # If mount-home flag is provided, mount user home directory inside container at same path
            container_spec_args['workingDir'] = home_path if not container_spec_args['workingDir'] else container_spec_args['workingDir']

        # Parse environment variables
        if hasattr(self.args, 'env') and self.args.env:
            env_vars = self._parse_env_arg(self.args.env)
            container_spec_args['env'].update(env_vars)

        # Parse volume mounts for container spec from pod_spec_args volumes
        for vol in pod_spec_args['volumes']:
            container_spec_args['volume_mounts'][vol['name']] = vol['mount_path']

        return {
            'job_details_args': job_details_args,
            'job_spec_args': job_spec_args,
            'pod_spec_args': pod_spec_args,
            'container_spec_args': container_spec_args,
            'ports': ports,
            'follow': self.args.follow if hasattr(self.args, 'follow') else False,
            'dry_run': self.args.dry_run if hasattr(self.args, 'dry_run') else False,
            'verbose': self.args.verbose if hasattr(self.args, 'verbose') else False,
            'save_template': self.args.save_template if hasattr(self.args, 'save_template') else False
        }


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