# Contains the base code to build YAML configs for jobs, pods, and containers

import logging

class ContainerBuilder():
    def __init__(self, name, image, image_pull_policy=None, command=None, args=None, env=None, volume_mounts=None, resources=None, is_initContainer=False, **kwargs):

        """
        Arguments:
            name (string): Name of the container 
            image (string): Container image to use
            image_pull_policy (string, optional): Image pull policy. One of 'Always', 'IfNotPresent', 'Never'. Defaults to None.
            command (string or list, optional): Command to run in the container. Defaults to None.
            args (string or list, optional): Arguments to the command. Defaults to None.
            env (dict, optional): Environment variables as env {var name: value pairs}. Defaults to None.
            volume_mounts (dict, optional): Volume mounts as {mount_name: mount_path}. Defaults to None.
            resources (dict, optional): Resource requests and limits. resources = {"cpu_request": x, "cpu_limit": y, 
                "memory_request": a, "memory_limit": b, "gpu_count": n, "gpu_type": t, "gpu_memory": m, "gpu_vendor": v}. Defaults to None.
            is_initContainer (bool, optional): Whether this container is an initContainer. Defaults to False.
            **kwargs: Additional keyword arguments for container spec.
        """

        self.name = name
        self.image = image
        self.image_pull_policy = image_pull_policy
        if image_pull_policy is None:
            logging.warning(f"Image pull policy not set for container {name}. Always pulls the image, if it uses 'latest' tag.")
        self.command = command if command else []
        self.args = args if args else []
        self.env = env if env else {}
        self.volume_mounts = volume_mounts if volume_mounts else {}
        self.resources = resources if resources else {}
        self.is_initContainer = is_initContainer
        self.kwargs = kwargs

        if self.is_initContainer:
            if {"livenessProbe", "readinessProbe", "startupProbe", "postStart", "preStop"} & self.kwargs.keys():
                raise ValueError("Probes and lifecycle hooks are not allowed in initContainers.")
            
            self.name = f"init-{self.name}"

    # TODO: Manage GPU Type.
    def build(self):
        container = {}

        container['name'] = self.name
        container['image'] = self.image
        if self.image_pull_policy:
            container['imagePullPolicy'] = self.image_pull_policy
        # Command: 
        if self.command:
            container['command'] = self.command.split() if isinstance(self.command, str) else self.command

        if self.args:
            container['args'] = [self.args.strip()] if isinstance(self.args, str) else self.args

        if self.env:
            container['env'] = [
                {'name': k, 'value': v} 
                 for k, v in self.env.items()
                ]
            
        if self.volume_mounts:
            container['volumeMounts'] = [
                {'name': k, 'mountPath': v} 
                 for k, v in self.volume_mounts.items()
                ]

        if self.resources:
            container['resources'] = self.set_resources(self.resources)

        for key, value in self.kwargs.items():
            container[key] = value

        return container
    
    def set_resources(self, resources):
        resource_dict = {}
        requests = {}
        limits = {}

        if 'cpu_request' in resources:
            requests['cpu'] = str(resources['cpu_request'])
        if 'cpu_limit' in resources:
            limits['cpu'] = str(resources['cpu_limit'])

        if 'memory_request' in resources:
            requests['memory'] = str(resources['memory_request'])
        if 'memory_limit' in resources:
            limits['memory'] = str(resources['memory_limit'])

        # Configuring GPU resources
        self._add_gpu_resources(resources, limits)
            
        resource_dict['requests'] = requests
        resource_dict['limits'] = limits

        return resource_dict
    
    def _add_gpu_resources(self, resources, limits):
        if 'gpu_count' in resources and 'gpu_memory' in resources:
            raise ValueError("Specify either 'gpu_count' or 'gpu_memory', not both.")
        
        gpu_vendor = self._get_gpu_vendor(resources.get('gpu_vendor', 'nvidia'))
        
        if 'gpu_count' in resources and resources['gpu_count'] is not None:
            gpu_count = resources['gpu_count']

            if float(gpu_count) <= 0:
                raise ValueError("'gpu_count' must be a positive integer.")

            if float(gpu_count) != int(gpu_count):
                if gpu_count < 1:
                    raise NotImplementedError("Setting fractional GPU counts is not yet supported in this version.")
                else:
                    raise ValueError("'gpu_count' must be an integer value if greater than 1.")

            limits[f"{gpu_vendor}/gpu"] = str(int(gpu_count))
        
        if 'gpu_memory' in resources:
            raise NotImplementedError("Setting GPU memory is not yet supported in this version.")

    def _get_gpu_vendor(self, vendor):
        vendor_map = {
            'nvidia': 'nvidia.com',
            'amd': 'amd.com',
        }
        vendor = vendor.lower()
        if vendor not in vendor_map:
            logging.warning(f"Unknown GPU vendor '{vendor}', defaulting to nvidia.com")
            return 'nvidia.com'
        return vendor_map[vendor]


class PodSpecBuilder():
    def __init__(self, containers, scheduler="kai-scheduler", restart_policy='Never', num_restarts=None, node_selectors=None, init_containers=None, volumes=None, **kwargs):

        """
        Initialize the pod spec
        Arguments:
            containers (list): List of container specs (dictionaries) for the pod.
            scheduler (string, optional): Scheduler to use. Defaults to "kai-scheduler".
            restart_policy (string, optional): Restart policy for the pod. One of 'Always', 'OnFailure', 'Never'. Defaults to 'Never'.
            num_restarts (int, optional): Number of pod restarts to allow. Defaults to None.
            node_selectors (dict, optional): Node selectors as {key: value} pairs. Defaults to None.
            init_containers (list, optional): List of init container specs (dictionaries). Defaults to None.
            volumes (list, optional): List of volume specs (dictionaries) as defined in https://kubernetes.io/docs/concepts/storage/volumes.
                Format is [{"name": "host-data", "volume_type": "hostPath", "read_only": True/False, "details": {"path": "/data", "type": "Directory"}}, ....]. Defaults to None.
            **kwargs: Additional keyword arguments for pod spec.
        """

        self.containers = containers
        self.scheduler = scheduler
        self.restart_policy = restart_policy
        self.num_restarts = num_restarts
        self.node_selectors = node_selectors if node_selectors else {}
        self.init_containers = init_containers if init_containers else []
        self.volumes = volumes if volumes else {}
        self.kwargs = kwargs

        # Validate restart policy
        valid_policies = ['Always', 'OnFailure', 'Never']
        if restart_policy not in valid_policies:
            raise ValueError(f"'restart_policy' must be one of {valid_policies}")

    # TODO: priority, priorityClassName, tolerations, affinity, imagePullSecrets, activeDeadlineSeconds, terminationGracePeriodSeconds
    # TODO: Support waiting for a different job/pod's completeion to schedule this pod using *init container* or mutating webhook
    def build(self):

        spec = {}

        # Scheduler
        if self.scheduler:
            spec['schedulerName'] = self.scheduler

        # Restart Policy
        spec['restartPolicy'] = self.restart_policy

        # Number of Restarts using init_container or mutating webhook to track restarts
        if self.num_restarts is not None:
            #TODO: Implement restart tracking using an init container or mutating webhook
            if self.restart_policy == 'Never':
                logging.warning("Ignoring 'num_restarts' since 'restart_policy' is set to 'Never'")
            logging.warning("'num_restarts' is set but not yet implemented for containers")

        # Node Selector
        if self.node_selectors:
            spec['nodeSelector'] = self.node_selectors

        # Init Containers
        if self.init_containers:
            spec['initContainers'] = self.init_containers

        # Containers
        if len(self.containers):
            spec['containers'] = self.containers
        else:
            raise ValueError("At least one container must be specified in the pod spec.")


        if self.volumes:
            spec['volumes'] = self._set_volumes(self.volumes)

        for key, value in self.kwargs.items():
            spec[key] = value

        return spec
    
    def _set_volumes(self, volumes):
        volume_list = []
        for vol in volumes:
            volume = {}
            volume['name'] = vol['name']
            vol_type = vol['volume_type']
            details = vol.get('details', {})

            if vol_type == 'emptyDir':
                volume['emptyDir'] = details
            elif vol_type == 'hostPath':
                volume['hostPath'] = details
            else:
                logging.warning(f"Volume type '{vol_type}' is not officially supported. Using it as is.")
                volume[vol_type] = details

            volume_list.append(volume)
        return volume_list
    

# TODO: completions, parallelism, completionMode, backoffLimitPerIndex, activeDeadlineSeconds, podFailurePolicy
# TODO: suspend (pause/resume the job), Others: podReplacementPolicy, manualSelector, selector, templateGeneration, revisionHistoryLimit, successPolicy
# NOTE: Default spec.template.metadata.labels.'kai.scheduler/queue': default-queue is set outside the Job builder and sent as kwargs
# NOTE: Default spec.template.metadata.annotations.priorityClassName: train is set outside the Job builder and sent as kwargs
class JobSpecBuilder():
    def __init__(self, pod_spec, backoff_limit=None, ttl_seconds_after_finished=1296000, **kwargs):
        self.pod_spec = pod_spec
        self.backoff_limit = backoff_limit
        self.ttl_seconds_after_finished = ttl_seconds_after_finished
        self.kwargs = kwargs

        if backoff_limit is not None and backoff_limit < 0:
            raise ValueError("'backoff_limit' must be >= 0")

    def build(self):
        job_spec = {}

        if self.backoff_limit is not None:
            job_spec['backoffLimit'] = self.backoff_limit
        job_spec['ttlSecondsAfterFinished'] = self.ttl_seconds_after_finished
        
        job_spec['template'] = {
            'spec': self.pod_spec
        }

        for key, value in self.kwargs.items():
            job_spec[key] = value

        return job_spec
    
class JobBuilder():
    def __init__(self, job_name, job_spec, namespace=None, api_version='batch/v1', kind='Job', labels=None, annotations=None, **kwargs):
        self.api_version = api_version
        self.kind = kind
        self.name = job_name
        self.namespace = namespace
        self.labels = labels if labels else {}
        self.annotations = annotations if annotations else {}
        self.job_spec = job_spec
        self.kwargs = kwargs

    def build(self):
        job = {}

        job['apiVersion'] = self.api_version
        job['kind'] = self.kind

        job['metadata'] = {}
        job['metadata']['name'] = self.name
        if self.namespace:
            job['metadata']['namespace'] = self.namespace
        if self.labels:
            job['metadata']['labels'] = self.labels
        if self.annotations:
            job['metadata']['annotations'] = self.annotations

        job['spec'] = self.job_spec

        for key, value in self.kwargs.items():
            job[key] = value

        return job
