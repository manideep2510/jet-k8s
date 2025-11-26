# Main file to get user cli arguments, submit job, print job status and underlying pods, capture other commands such as get, describe, exec, logs, delete, etc.
# and call relevant functions from other modules

import argparse
from .utils import print_job_yaml, submit_job, wait_for_job_pods_ready, get_logs, delete_resource, init_pod_object, exec_into_pod, TemplateManager
from .job_builder import ContainerBuilder, PodSpecBuilder, JobSpecBuilder, JobBuilder
from .process_args import ProcessArguments
import time
import signal


def parse_arguments():
    parser = argparse.ArgumentParser(description="Jet CLI Tool")
    subparsers = parser.add_subparsers(dest='jet_command')

    # Launch command
    launch_parser = subparsers.add_parser('launch', help='Launch a job or jupyter server')
    launch_subparsers = launch_parser.add_subparsers(dest='launch_type')

    # Launch Job
    job_parser = launch_subparsers.add_parser('job', help='Launch a job')
    job_parser.add_argument('name', help='Name of the job or path to job file')
    job_parser.add_argument('--template', help='Name of the job template to use. A template name saved by jet at ~/.jet/templates/ or a full path to a job yaml file.')
    job_parser.add_argument('--namespace', '-n', help='Kubernetes namespace')
    job_parser.add_argument('--image', help='Container image name')
    job_parser.add_argument('--image-pull-policy', choices=['IfNotPresent', 'Always', 'Never'], help='Image pull policy')
    job_parser.add_argument('--command', help='Command to run in the container')
    job_parser.add_argument('--shell', default='/bin/sh', help='Shell to use for the command')
    job_parser.add_argument('--pyenv', help='Path to Python environment. Supported envs: conda, venv, uv.')
    job_parser.add_argument('--scheduler', default='kai-scheduler', help='Scheduler name')
    job_parser.add_argument('--priority', default='train', help='Job priority')
    job_parser.add_argument('--restart-policy', choices=['Never', 'OnFailure', 'Always'], default='Never', help='Pod restart policy')
    job_parser.add_argument('--volume', '-v', action='append', nargs='+', help='Volumes to mount. Format: [<volume_name>:]<host_path>[:<mount_path>][:Type]')
    job_parser.add_argument('--working-dir', help='Working directory inside the container')
    job_parser.add_argument('--shm-size', help='Size of /dev/shm')
    job_parser.add_argument('--env', nargs='+', action='append', help='Environment variables or env file')
    job_parser.add_argument('--cpu', default='1:1', help='CPU request and limit. Format: request[:limit]')
    job_parser.add_argument('--memory', default='4Gi:4Gi', help='Memory request and limit. Format: request[:limit]')
    job_parser.add_argument('--gpu', help='Number of GPUs to request')
    job_parser.add_argument('--gpu-type', help='Type of GPU to request')
    job_parser.add_argument('--node-selector', action='append', nargs='+', help='Node selector labels in key=value format')
    job_parser.add_argument('--mount-home', action='store_true', help='If provided, user home directory will be mounted inside the container at the same path')
    job_parser.add_argument('--follow', '-f', action='store_true', help='Follow job logs')
    job_parser.add_argument('--dry-run', action='store_true', help='If provided, job yaml will be printed but not submitted')
    job_parser.add_argument('--verbose', action='store_true', help='If provided, YAML and other debug info will be printed')
    job_parser.add_argument('--save-template', action='store_true', help='If provided, job yaml will be saved to ~/.jet/templates/')

    # Launch Jupyter
    jupyter_parser = launch_subparsers.add_parser('jupyter', help='Launch a Jupyter Notebook server')
    jupyter_parser.add_argument('name', help='Name of the Jupyter job')
    jupyter_parser.add_argument('--template', help='Name of the Jupyter job template to use. A template name saved by jet at ~/.jet/templates/ or a full path to a job yaml file.')
    jupyter_parser.add_argument('--namespace', '-n', help='Kubernetes namespace')
    jupyter_parser.add_argument('--image', help='Container image name')
    jupyter_parser.add_argument('--image-pull-policy', choices=['IfNotPresent', 'Always', 'Never'], help='Image pull policy')
    jupyter_parser.add_argument('--pyenv', help='Path to Python environment. Supported envs: conda, venv, uv.')
    jupyter_parser.add_argument('--scheduler', default='kai-scheduler', help='Scheduler name')
    jupyter_parser.add_argument('--port', default='8888', help='Optional host port number to forward the port 8888 of Jupyter server inside the pod and optional Jupyter port to customize port inside pod. Format: [forward_port]:[jupyter_port]')
    jupyter_parser.add_argument('--notebooks-dir', '-nd', help='Path to Jupyter notebooks directory on host machine to mount inside the container')
    jupyter_parser.add_argument('--volume', '-v', action='append', nargs='+', help='Additional volumes to mount. Format: [<volume_name>:]<host_path>[:<mount_path>][:Type]')
    jupyter_parser.add_argument('--shm-size', help='Size of /dev/shm')
    jupyter_parser.add_argument('--env', nargs='+', action='append', help='Environment variables or env file')
    jupyter_parser.add_argument('--cpu', default='1:1', help='CPU request and limit. Format: request[:limit]')
    jupyter_parser.add_argument('--memory', default='4Gi:4Gi', help='Memory request and limit. Format: request[:limit]')
    jupyter_parser.add_argument('--gpu', help='Number of GPUs to request')
    jupyter_parser.add_argument('--gpu-type', help='Type of GPU to request')
    jupyter_parser.add_argument('--node-selector', action='append', nargs='+', help='Node selector labels in key=value format')
    jupyter_parser.add_argument('--mount-home', action='store_true', help='If provided, user home directory will be mounted inside the container at the same path')
    jupyter_parser.add_argument('--token', help='Jupyter Notebook token')
    jupyter_parser.add_argument('--follow', '-f', action='store_true', help='Follow job logs')
    jupyter_parser.add_argument('--dry-run', action='store_true', help='If provided, job yaml will be printed but not submitted')
    jupyter_parser.add_argument('--verbose', action='store_true', help='If provided, YAML and other debug info will be printed')
    jupyter_parser.add_argument('--save-template', action='store_true', help='If provided, job yaml will be saved to ~/.jet/templates/')

    # Launch Debug session
    debug_parser = launch_subparsers.add_parser('debug', help='Launch a debug session')
    debug_parser.add_argument('name', help='Name of the debug job')
    debug_parser.add_argument('--template', help='Name of the debug job template to use. A template name saved by jet at ~/.jet/templates/ or a full path to a job yaml file.')
    debug_parser.add_argument('--namespace', '-n', help='Kubernetes namespace')
    debug_parser.add_argument('--image', help='Container image name')
    debug_parser.add_argument('--image-pull-policy', choices=['IfNotPresent', 'Always', 'Never'], help='Image pull policy')
    debug_parser.add_argument('--duration', type=int, default=21600, help='Duration of the debug session in seconds (default: 21600 seconds = 6 hours)')
    debug_parser.add_argument('--shell', default='/bin/sh', help='Shell to use for the debug session. If zsh is required, user must provide image with zsh installed, set --shell /bin/zsh, and mount user home/zsh files if needed using --volume flag')
    debug_parser.add_argument('--pyenv', help='Path to Python environment. Supported envs: conda, venv, uv.')
    debug_parser.add_argument('--scheduler', default='kai-scheduler', help='Scheduler name')
    debug_parser.add_argument('--volume', '-v', action='append', nargs='+', help='Volumes to mount. Format: [<volume_name>:]<host_path>[:<mount_path>][:Type]')
    debug_parser.add_argument('--working-dir', help='Working directory inside the container')
    debug_parser.add_argument('--shm-size', help='Size of /dev/shm')
    debug_parser.add_argument('--env', nargs='+', action='append', help='Environment variables or env file')
    debug_parser.add_argument('--cpu', default='1:1', help='CPU request and limit. Format: request[:limit]')
    debug_parser.add_argument('--memory', default='4Gi:4Gi', help='Memory request and limit. Format: request[:limit]')
    debug_parser.add_argument('--gpu', help='Number of GPUs to request')
    debug_parser.add_argument('--gpu-type', help='Type of GPU to request')
    debug_parser.add_argument('--node-selector', action='append', nargs='+', help='Node selector labels in key=value format')
    debug_parser.add_argument('--mount-home', action='store_true', help='If provided, user home directory will be mounted inside the container at the same path')
    debug_parser.add_argument('--follow', '-f', action='store_true', help='Follow job logs')
    debug_parser.add_argument('--dry-run', action='store_true', help='If provided, job yaml will be printed but not submitted')
    debug_parser.add_argument('--verbose', action='store_true', help='If provided, YAML and other debug info will be printed')
    debug_parser.add_argument('--save-template', action='store_true', help='If provided, job yaml will be saved to ~/.jet/templates/')

    # List templates command
    list_templates_parser = subparsers.add_parser('list-templates', help='List available job templates')
    list_templates_parser.add_argument('--type', choices=['job', 'jupyter', 'debug'], help='Type of templates to list')
    list_templates_parser.add_argument('--name', help='Filter templates by name (substring match)')
    list_templates_parser.add_argument('--regex', help='Filter templates by regex pattern')
    list_templates_parser.add_argument('--sort-by', choices=['time', 'name'], default='time', help='Sort templates by time or name')
    list_templates_parser.add_argument('--verbose', '-v', action='store_true', help='Show detailed template information')

    # Get command
    get_parser = subparsers.add_parser('get', help='Get job or pod status')
    get_parser.add_argument('name', help='Name of the job or pod')
    get_parser.add_argument('--level', choices=['all', 'pods', 'jobs'], default='all', help='Level of status detail')
    get_parser.add_argument('--namespace', help='Kubernetes namespace')

    # Logs command
    logs_parser = subparsers.add_parser('logs', help='Get logs from a pod')
    logs_parser.add_argument('pod_name', help='Name of the pod')
    logs_parser.add_argument('--job', help='Name of the job')
    logs_parser.add_argument('--follow', '-f', action='store_true', help='Follow logs output')
    logs_parser.add_argument('--namespace', help='Kubernetes namespace')

    # Describe command
    # jet describe job <name> or jet describe pod <name>
    # TODO: Should it be jet describe <job_name> or <pod_name> with an additional argument to specify type? Or for job, its "jet describe <job_name>", but for pod, it is "jet describe pod <pod_name>"
    describe_parser = subparsers.add_parser('describe', help='Describe a job or pod details')
    describe_parser.add_argument('resource_type', choices=['job', 'pod'], help='Type of resource to describe. If job is provided, job details will be described along ability to choose underlying pods for details.')
    describe_parser.add_argument('name', help='Name of the job or pod')
    describe_parser.add_argument('--namespace', help='Kubernetes namespace')

    # Connect command
    # jet connect <job_name> or jet connect pod <pod_name>
    # TODO: Should it be jet describe <job_name> or <pod_name> with an additional argument to specify type? Or for job, its "jet describe <job_name>", but for pod, it is "jet describe pod <pod_name>"
    # TODO: Or for connect, should it just be jet connect <job_name>, as debug jobs have only one pod.
    connect_parser = subparsers.add_parser('connect', help='Execute into a debug session')
    connect_parser.add_argument('resource_type', choices=['job', 'pod'], help='Type of resource to connect to. If job is provided, user will be able to select underlying pod to connect to.')
    connect_parser.add_argument('name', help='Name of the job or pod')
    connect_parser.add_argument('--namespace', help='Kubernetes namespace')

    # Delete command
    # jet delete <job_name> or jet delete pod <pod_name>
    delete_parser = subparsers.add_parser('delete', help='Delete a job')
    delete_parser.add_argument('resource_type', choices=['job', 'pod'], help='Type of resource to delete. If job is provided, the job and all underlying pods will be deleted.')
    delete_parser.add_argument('name', help='Name of the job or pod')
    delete_parser.add_argument('--namespace', help='Kubernetes namespace')

    return parser.parse_args()


class Jet():
    def __init__(self, processed_args):
        self.processed_args = processed_args
        self.template_manager = TemplateManager()

    def launch_job(self):

        job_details_args = self.processed_args['job_details_args']
        job_spec_args = self.processed_args['job_spec_args']
        pod_spec_args = self.processed_args['pod_spec_args']
        container_spec_args = self.processed_args['container_spec_args']
        follow = self.processed_args['follow']
        save_template = self.processed_args['save_template']

        container_specs = ContainerBuilder(**container_spec_args).build()
        pod_spec_args['containers'] = [container_specs]
        pod_spec = PodSpecBuilder(**pod_spec_args).build()
        job_spec_args['pod_spec'] = pod_spec
        job_spec = JobSpecBuilder(**job_spec_args).build()
        job_builder = JobBuilder(**job_details_args, job_spec=job_spec)
        job_config = job_builder.build()

        if save_template:
            self.template_manager.save_job_template(
                job_config=job_config,
                job_name=job_details_args['job_name'],
                job_type='job',
                verbose=self.processed_args['verbose']
            )
            return

        # Submit the job
        submit_job(
            job_config=job_config,
            dry_run=self.processed_args['dry_run'],
            verbose=self.processed_args['verbose']
        )

        # Return if dry run
        if self.processed_args['dry_run']:
            return

        # TODO: If follow is True, implement logic to follow job logs, status and events in addition to below pod log streaming.
        if follow:
            # Wait for job pods to be running
            print("Waiting for job pods to be ready...")
            pod_name = wait_for_job_pods_ready(
                            job_name=job_details_args['job_name'],
                            namespace=job_details_args['namespace'],
                            timeout=300
                        )

            print(f"Job pod \x1b[1;38;2;30;144;255m{pod_name}\x1b[0m is running\n")

            print(f"Streaming logs from pod \x1b[1;38;2;30;144;255m{pod_name}\x1b[0m. Use Control-C to stop streaming.\n")

            # Stream logs from all pods
            get_logs(
                pod_name=pod_name,
                namespace=job_details_args['namespace'],
                follow=True,
                timeout=None
            )

    def launch_jupyter(self):
        
        job_details_args = self.processed_args['job_details_args']
        job_spec_args = self.processed_args['job_spec_args']
        pod_spec_args = self.processed_args['pod_spec_args']
        container_spec_args = self.processed_args['container_spec_args']
        pod_port = [item for item in self.processed_args['ports'] if item['name'] == 'jupyter'][0]['container_port']
        host_port = [item for item in self.processed_args['ports'] if item['name'] == 'jupyter'][0]['host_port']
        follow = self.processed_args['follow']
        save_template = self.processed_args['save_template']

        container_specs = ContainerBuilder(**container_spec_args).build()
        pod_spec_args['containers'] = [container_specs]
        pod_spec = PodSpecBuilder(**pod_spec_args).build()
        job_spec_args['pod_spec'] = pod_spec
        job_spec = JobSpecBuilder(**job_spec_args).build()
        job_builder = JobBuilder(**job_details_args, job_spec=job_spec)
        job_config = job_builder.build()

        if save_template:
            self.template_manager.save_job_template(
                job_config=job_config,
                job_name=job_details_args['job_name'],
                job_type='jupyter',
                verbose=self.processed_args['verbose']
            )
            return

        # Submit the job
        submit_job(
            job_config=job_config,
            dry_run=self.processed_args['dry_run'],
            verbose=self.processed_args['verbose']
        )

        # Return if dry run
        if self.processed_args['dry_run']:
            return

        # TODO: Watch for job and pod status. If any of them fail or deleted EXTERNALLY, stop port forwarding and exit gracefully.
        # TODO: If follow is True, implement logic to follow job logs, status and events in addition to below pod log streaming.

        try:
            # Wait for Jupyter pod to be running
            print("Waiting for Jupyter pod to be ready...")
            jupyter_pod_name = wait_for_job_pods_ready(
                                job_name=job_details_args['job_name'],
                                namespace=job_details_args['namespace'],
                                timeout=300
                            )
            print(f"Jupyter pod \x1b[1;38;2;30;144;255m{jupyter_pod_name}\x1b[0m is running\n")

            # Forward port from host to pod
            pod = init_pod_object(resource=jupyter_pod_name, namespace=job_details_args['namespace'])
            port_forwarder = pod.portforward(remote_port=pod_port, local_port=host_port)
            port_forwarder.start()
            print(f"Forwarding from local port {host_port} to pod {jupyter_pod_name} port {pod_port}\n")

            # Stream Jupyter logs
            get_logs(
                pod_name=jupyter_pod_name,
                namespace=job_details_args['namespace'],
                follow=True,
                timeout=None if follow else 15 # No timeout for follow, 15 seconds for non-follow to capture token
            )

            # Keep the port forwarding running
            print(f"\nJupyter server is running. Access it at: http://localhost:{host_port}. Check the logs for the token if not provided.")
            print("Use Control-C to stop and delete the Jupyter job")
            while True:
                time.sleep(1)

        # Catch any exception during jupyter server creation or keyboard interrupt
        # TODO: These exception handlings would remove a currently running job elsewhere in the namespace with the same name, if the user did not change the job name by mistake. Need to handle this better.
        # TODO: If port forwarding fails, the job/pod is still running. Need to handle that better.
        # TODO: Handle graceful shutdown of jupyter server inside the pod before deleting the job/pod (saving checkpoints, etc.)
        # BUG: The exception handlings are not obscuring teh case where the job is not even there and prints misleading message. Need to handle that better.
        except KeyboardInterrupt:
            print("Keyboard interrupt received... \n\nDeleting Jupyter job/pod")

            # Block further interrupts while cleaning up
            # NOTE: For robustness, reset signal handler after cleanup.
            signal.signal(signal.SIGINT, signal.SIG_IGN)

            port_forwarder.stop()
            try:
                delete_resource(
                    name=job_details_args['job_name'],
                    resource_type='job',
                    namespace=job_details_args['namespace']
                )
            except Exception as delete_exception:

                print(f"Error deleting Jupyter job/pod: {delete_exception}")

        except Exception as e:
            # Delete jupyter job/pod if created
            print(f"Error occurred during jupyter server creation or running it: {e}. \n\nDeleting Jupyter job/pod if created")
            port_forwarder.stop()

            # Block interrupts while cleaning up.
            # NOTE: For robustness, reset signal handler after cleanup.
            signal.signal(signal.SIGINT, signal.SIG_IGN)

            try:
                delete_resource(
                    name=job_details_args['job_name'],
                    resource_type='job',
                    namespace=job_details_args['namespace']
                )
            except Exception as delete_exception:
                print(f"Error deleting Jupyter job/pod: {delete_exception}")
            raise e

    def launch_debug(self):
        
        job_details_args = self.processed_args['job_details_args']
        job_spec_args = self.processed_args['job_spec_args']
        pod_spec_args = self.processed_args['pod_spec_args']
        container_spec_args = self.processed_args['container_spec_args']
        follow = self.processed_args['follow']
        save_template = self.processed_args['save_template']

        container_specs = ContainerBuilder(**container_spec_args).build()
        pod_spec_args['containers'] = [container_specs]
        pod_spec = PodSpecBuilder(**pod_spec_args).build()
        job_spec_args['pod_spec'] = pod_spec
        job_spec = JobSpecBuilder(**job_spec_args).build()
        job_builder = JobBuilder(**job_details_args, job_spec=job_spec)
        job_config = job_builder.build()

        if save_template:
            self.template_manager.save_job_template(
                job_config=job_config,
                job_name=job_details_args['job_name'],
                job_type='debug',
                verbose=self.processed_args['verbose']
            )
            return

        # Submit the job
        submit_job(
            job_config=job_config,
            dry_run=self.processed_args['dry_run'],
            verbose=self.processed_args['verbose']
        )

        # Return if dry run
        if self.processed_args['dry_run']:
            return

        # TODO: If follow is True, implement logic to follow job logs, status and events.
        # TODO: Exec only if a connect argument is passed. Yet to implement.

        try:
            # Wait for debug pod to be running
            print("Waiting for debug pod to be ready...")
            debug_pod_name = wait_for_job_pods_ready(
                                job_name=job_details_args['job_name'],
                                namespace=job_details_args['namespace'],
                                timeout=300
                            )
            print(f"Debug pod \x1b[1;38;2;30;144;255m{debug_pod_name}\x1b[0m is running\n")

            # Exec into the debug pod with the specified shell
            print(f"Connecting to debug pod \x1b[1;38;2;30;144;255m{debug_pod_name}\x1b[0m. Use \x1b[1;33mexit\x1b[0m to terminate the session and delete the debug job.\n")
            exec_into_pod(
                pod_name=debug_pod_name,
                namespace=job_details_args['namespace'],
                shell=container_spec_args['command'].split(' ')[0] # Extract shell from command
            )

            # After exiting the exec session, delete the debug job/pod
            print("\nDebug session ended. Deleting debug job/pod...")
            delete_resource(
                name=job_details_args['job_name'],
                resource_type='job',
                namespace=job_details_args['namespace']
            )

        # Catch any exception during debug session creation or keyboard interrupt
        # TODO: These exception handlings would remove a currently running job elsewhere in the namespace with the same name, if the user did not change the job name by mistake. Need to handle this better.
        # BUG: The exception handlings are not obscuring teh case where the job is not even there and prints misleading message. Need to handle that better.
        except KeyboardInterrupt:
            print("Keyboard interrupt received... \n\nDeleting debug job/pod")

            # Block further interrupts while cleaning up
            # NOTE: For robustness, reset signal handler after cleanup.
            signal.signal(signal.SIGINT, signal.SIG_IGN)

            delete_resource(
                name=job_details_args['job_name'],
                resource_type='job',
                namespace=job_details_args['namespace']
            )

        except Exception as e:
            print(f"Error occurred during creation or running of debug session: {e}. \n\nDeleting debug job/pod if created")

            # Block interrupts while cleaning up.
            # NOTE: For robustness, reset signal handler after cleanup.
            signal.signal(signal.SIGINT, signal.SIG_IGN)

            delete_resource(
                name=job_details_args['job_name'],
                resource_type='job',
                namespace=job_details_args['namespace']
            )

    # TODO: Yet to implement
    def get_status(self):
        pass

    # TODO: Yet to implement
    def get_logs(self):
        pass

    # TODO: Yet to implement
    def describe(self):
        pass

    # TODO: Yet to implement
    def connect(self):
        pass

    # TODO: Yet to implement
    def delete(self):
        pass

def run(args, command, launch_type=None):
    # Jet instance
    jet = Jet(processed_args=args)

    # Execute commands
    if command == 'launch':
        if launch_type == 'job':
            jet.launch_job()
        elif launch_type == 'jupyter':
            jet.launch_jupyter()
        elif launch_type == 'debug':
            jet.launch_debug()
    elif command == 'get':
        jet.get_status()
    elif command == 'logs':
        jet.get_logs()
    elif command == 'describe':
        jet.describe()
    elif command == 'connect':
        jet.connect()
    elif command == 'delete':
        jet.delete()

def cli():
    
    # Command line arguments
    args = parse_arguments()

    # Process arguments
    processor = ProcessArguments(args)
    processed_args = processor.process()

    # Run Jet commands
    run(processed_args, args.jet_command,
        args.launch_type if hasattr(args, 'launch_type') else None)

if __name__ == "__main__":
    cli()