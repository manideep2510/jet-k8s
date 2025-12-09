# Main file to get user cli arguments, submit job, print job status and underlying pods, capture other commands such as get, describe, exec, logs, delete, etc.
# and call relevant functions from other modules

import argparse
import subprocess
from .utils import print_job_yaml, submit_job, wait_for_job_pods_ready, get_logs, delete_resource, init_pod_object, exec_into_pod, TemplateManager, detect_shell, get_kubeconfig, get_current_namespace
from .process_args import ProcessArguments
from .tui.app import run_tui
import time
import signal
from .defaults import JET_HOME


def get_kubectl_help(command):
    """Fetch kubectl help output for a given command."""
    try:
        result = subprocess.run(
            ['kubectl', command, '--help'],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.stdout
    except Exception:
        return None


def make_kubectl_help_formatter(kubectl_command):
    """Factory function to create a formatter class with a specific kubectl command."""
    class KubectlHelpFormatter(argparse.RawDescriptionHelpFormatter):
        """Custom formatter that appends kubectl help output."""
        
        def format_help(self):
            help_text = super().format_help()
            
            kubectl_help = get_kubectl_help(kubectl_command)
            if kubectl_help:
                help_text += f"\nkubectl {kubectl_command} options:\n"
                help_text += kubectl_help
            
            return help_text
    
    return KubectlHelpFormatter


def parse_arguments():

    # Note: No default values are set here for any arguments, as defaults are handled in process_args.py based on template or default values.
    parser = argparse.ArgumentParser(description="Jet CLI")
    subparsers = parser.add_subparsers(dest='jet_command')

    # Store parser references for printing help when needed
    parser._subparsers_map = {}

    # Launch command
    launch_parser = subparsers.add_parser('launch', help='Launch a job or jupyter server')
    launch_subparsers = launch_parser.add_subparsers(dest='launch_type')
    parser._subparsers_map['launch'] = launch_parser

    # Launch Job
    job_parser = launch_subparsers.add_parser('job', help='Launch a job')
    job_parser.add_argument('name', nargs='?', help='Name of the job or path to job file')
    parser._subparsers_map['launch_job'] = job_parser
    job_parser.add_argument('--template', help='Name of the job template to use. A template name saved by jet at ~/.local/share/jet/templates/ or $XDG_DATA_HOME/jet/templates/ or a full path to a job yaml file.')
    job_parser.add_argument('--namespace', '-n', help='Kubernetes namespace')
    job_parser.add_argument('--image', help='Container image name')
    job_parser.add_argument('--image-pull-policy', choices=['IfNotPresent', 'Always', 'Never'], help='Image pull policy')
    job_parser.add_argument('--command', help='Command to run in the container')
    job_parser.add_argument('--shell', help='Shell to use for the command')
    job_parser.add_argument('--pyenv', help='Path to Python environment. Supported envs: conda, venv, uv.')
    job_parser.add_argument('--scheduler', help='Scheduler name')
    job_parser.add_argument('--priority', help='Job priority')
    job_parser.add_argument('--restart-policy', choices=['Never', 'OnFailure', 'Always'], help='Pod restart policy')
    job_parser.add_argument('--volume', '-v', action='append', nargs='+', help='Volumes to mount. Format: [<volume_name>:]<host_path>[:<mount_path>][:Type]')
    job_parser.add_argument('--working-dir', help='Working directory inside the container')
    job_parser.add_argument('--shm-size', help='Size of /dev/shm shared memory')
    job_parser.add_argument('--env', nargs='+', action='append', help='Environment variables or env file')
    job_parser.add_argument('--cpu', help='CPU request and limit. Format: request[:limit]')
    job_parser.add_argument('--memory', '--mem', help='Memory request and limit. Format: request[:limit]')
    job_parser.add_argument('--gpu', help='Number of GPUs to request')
    job_parser.add_argument('--gpu-type', help='Type of GPU to request')
    job_parser.add_argument('--node-selector', action='append', nargs='+', help='Node selector labels in key=value format')
    job_parser.add_argument('--mount-home', action='store_true', help='If provided, user home directory will be mounted inside the container at the same path')
    job_parser.add_argument('--follow', '-f', action='store_true', help='Follow job logs')
    job_parser.add_argument('--dry-run', action='store_true', help='If provided, job yaml will be printed but not submitted')
    job_parser.add_argument('--verbose', action='store_true', help='If provided, YAML and other debug info will be printed')
    job_parser.add_argument('--save-template', '-st', action='store_true', help='If provided, job yaml will be saved to ~/.local/share/jet/templates/ or $XDG_DATA_HOME/jet/templates/')

    # Launch Jupyter
    jupyter_parser = launch_subparsers.add_parser('jupyter', help='Launch a Jupyter Notebook server')
    jupyter_parser.add_argument('name', nargs='?', help='Name of the Jupyter job')
    parser._subparsers_map['launch_jupyter'] = jupyter_parser
    jupyter_parser.add_argument('--template', help='Name of the Jupyter job template to use. A template name saved by jet at ~/.local/share/jet/templates/ or $XDG_DATA_HOME/jet/templates/ or a full path to a job yaml file.')
    jupyter_parser.add_argument('--namespace', '-n', help='Kubernetes namespace')
    jupyter_parser.add_argument('--image', help='Container image name')
    jupyter_parser.add_argument('--image-pull-policy', choices=['IfNotPresent', 'Always', 'Never'], help='Image pull policy')
    jupyter_parser.add_argument('--pyenv', help='Path to Python environment. Supported envs: conda, venv, uv.')
    jupyter_parser.add_argument('--scheduler', help='Scheduler name')
    jupyter_parser.add_argument('--priority', help='Job priority class name')
    jupyter_parser.add_argument('--port', help='Optional host port number to forward the port 8888 of Jupyter server inside the pod and optional Jupyter port to customize port inside pod. Format: [forward_port]:[jupyter_port]')
    jupyter_parser.add_argument('--notebooks-dir', '-nd', help='Path to Jupyter notebooks directory on host machine to mount inside the container')
    jupyter_parser.add_argument('--volume', '-v', action='append', nargs='+', help='Additional volumes to mount. Format: [<volume_name>:]<host_path>[:<mount_path>][:Type]')
    jupyter_parser.add_argument('--shm-size', help='Size of /dev/shm shared memory')
    jupyter_parser.add_argument('--env', nargs='+', action='append', help='Environment variables or env file')
    jupyter_parser.add_argument('--cpu', help='CPU request and limit. Format: request[:limit]')
    jupyter_parser.add_argument('--memory', '--mem', help='Memory request and limit. Format: request[:limit]')
    jupyter_parser.add_argument('--gpu', help='Number of GPUs to request')
    jupyter_parser.add_argument('--gpu-type', help='Type of GPU to request')
    jupyter_parser.add_argument('--node-selector', action='append', nargs='+', help='Node selector labels in key=value format')
    jupyter_parser.add_argument('--mount-home', action='store_true', help='If provided, user home directory will be mounted inside the container at the same path')
    jupyter_parser.add_argument('--token', help='Jupyter Notebook token')
    jupyter_parser.add_argument('--follow', '-f', action='store_true', help='Follow job logs')
    jupyter_parser.add_argument('--dry-run', action='store_true', help='If provided, job yaml will be printed but not submitted')
    jupyter_parser.add_argument('--verbose', action='store_true', help='If provided, YAML and other debug info will be printed')
    jupyter_parser.add_argument('--save-template', '-st', action='store_true', help='If provided, job yaml will be saved to ~/.local/share/jet/templates/ or $XDG_DATA_HOME/jet/templates/')

    # Launch Debug session
    debug_parser = launch_subparsers.add_parser('debug', help='Launch a debug session')
    debug_parser.add_argument('name', nargs='?', help='Name of the debug job')
    parser._subparsers_map['launch_debug'] = debug_parser
    debug_parser.add_argument('--template', help='Name of the debug job template to use. A template name saved by jet at ~/.local/share/jet/templates/ or $XDG_DATA_HOME/jet/templates/ or a full path to a job yaml file.')
    debug_parser.add_argument('--namespace', '-n', help='Kubernetes namespace')
    debug_parser.add_argument('--image', help='Container image name')
    debug_parser.add_argument('--image-pull-policy', choices=['IfNotPresent', 'Always', 'Never'], help='Image pull policy')
    debug_parser.add_argument('--duration', type=int, help='Duration of the debug session in seconds (default: 21600 seconds = 6 hours)')
    debug_parser.add_argument('--shell', help='Shell to use for the debug session. If zsh is required, user must provide image with zsh installed, set --shell /bin/zsh, and mount user home/zsh files if needed using --volume flag')
    debug_parser.add_argument('--pyenv', help='Path to Python environment. Supported envs: conda, venv, uv.')
    debug_parser.add_argument('--scheduler', help='Scheduler name')
    debug_parser.add_argument('--priority', help='Job priority class name')
    debug_parser.add_argument('--volume', '-v', action='append', nargs='+', help='Volumes to mount. Format: [<volume_name>:]<host_path>[:<mount_path>][:Type]')
    debug_parser.add_argument('--working-dir', help='Working directory inside the container')
    debug_parser.add_argument('--shm-size', help='Size of /dev/shm shared memory')
    debug_parser.add_argument('--env', nargs='+', action='append', help='Environment variables or env file')
    debug_parser.add_argument('--cpu', help='CPU request and limit. Format: request[:limit]')
    debug_parser.add_argument('--memory', '--mem', help='Memory request and limit. Format: request[:limit]')
    debug_parser.add_argument('--gpu', help='Number of GPUs to request')
    debug_parser.add_argument('--gpu-type', help='Type of GPU to request')
    debug_parser.add_argument('--node-selector', action='append', nargs='+', help='Node selector labels in key=value format')
    debug_parser.add_argument('--mount-home', action='store_true', help='If provided, user home directory will be mounted inside the container at the same path')
    debug_parser.add_argument('--follow', '-f', action='store_true', help='Follow job logs')
    debug_parser.add_argument('--dry-run', action='store_true', help='If provided, job yaml will be printed but not submitted')
    debug_parser.add_argument('--verbose', action='store_true', help='If provided, YAML and other debug info will be printed')
    debug_parser.add_argument('--save-template', '-st', action='store_true', help='If provided, job yaml will be saved to ~/.local/share/jet/templates/ or $XDG_DATA_HOME/jet/templates/')

    # List command
    list_parser = subparsers.add_parser('list', help='List resources (templates, jobs, or pods). Defaults to listing jobs if no subcommand is provided.')
    list_parser.add_argument('--namespace', '-n', help='Kubernetes namespace (used when listing jobs or pods)')
    list_subparsers = list_parser.add_subparsers(dest='list_type')

    # List templates
    list_templates_parser = list_subparsers.add_parser('templates', aliases=['template', 'te', 't'], help='List available job templates')
    list_templates_parser.add_argument('--type', choices=['job', 'jupyter', 'debug'], help='Type of templates to list')
    list_templates_parser.add_argument('--name', help='Filter templates by name (substring match)')
    list_templates_parser.add_argument('--regex', help='Filter templates by regex pattern')
    list_templates_parser.add_argument('--sort-by', choices=['time', 'name'], default='name', help='Sort templates by time or name')
    list_templates_parser.add_argument('--verbose', '-v', action='store_true', help='Show detailed template information')

    # List jobs
    list_jobs_parser = list_subparsers.add_parser('jobs', aliases=['job', 'jo', 'j'], help='List Kubernetes jobs')
    list_jobs_parser.add_argument('--namespace', '-n', help='Kubernetes namespace')

    # List pods
    list_pods_parser = list_subparsers.add_parser('pods', aliases=['pod', 'po', 'p'], help='List Kubernetes pods')
    list_pods_parser.add_argument('--namespace', '-n', help='Kubernetes namespace')

    # Logs command
    # jet logs <job_name> (defaults to job) or jet logs pod <pod_name>
    logs_parser = subparsers.add_parser('logs', help='Get logs from a job or pod. If no resource type is provided (Examples: `jet logs my-job`), defaults to job.',
                                        formatter_class=make_kubectl_help_formatter('logs'))
    logs_parser.add_argument('logs_args', nargs=argparse.REMAINDER, metavar='ARG', help='[resource_type] <name> [kubectl_options]. Examples: "my-job", "job my-job", "pod my-pod -f".')
    parser._subparsers_map['logs'] = logs_parser

    # Describe command
    # Just passing through to kubectl, Pass all args after 'describe' to kubectl
    describe_parser = subparsers.add_parser('describe', help='Describe a job or pod',
                                            formatter_class=make_kubectl_help_formatter('describe'))
    describe_parser.add_argument('describe_args', nargs=argparse.REMAINDER, help='<resource_type> <name> [options]. Examples: "job my-job", "pod my-pod -n namespace".')
    parser._subparsers_map['describe'] = describe_parser

    # Connect command
    # jet connect <job_name> (defaults to job) or jet connect pod <pod_name>
    connect_parser = subparsers.add_parser('connect', help='Execute into a debug session. If no resource type is provided (Examples: `jet connect my-job`), defaults to job.')
    connect_parser.add_argument('connect_args', nargs='*', metavar='ARG', help='[resource_type] <name>. Examples: "my-job", "job my-job", "pod my-pod".')
    connect_parser.add_argument('--namespace', '-n', help='Kubernetes namespace')
    parser._subparsers_map['connect'] = connect_parser

    # Delete command
    # jet delete <job_name> (defaults to job) or jet delete pod <pod_name>
    delete_parser = subparsers.add_parser('delete', help='Delete a job or pod. If no resource type is provided (Examples: `jet delete my-job`), defaults to job.',
                                          formatter_class=make_kubectl_help_formatter('delete'))
    delete_parser.add_argument('delete_args', nargs=argparse.REMAINDER, metavar='ARG', help='[resource_type] <name> [kubectl_options]. Examples: "my-job", "job my-job", "pod my-pod --force".')
    parser._subparsers_map['delete'] = delete_parser

    return parser, parser.parse_args()


def print_help_and_exit(parser, subparser_key=None):
    """Helper function to print help message and exit."""
    if subparser_key and subparser_key in parser._subparsers_map:
        parser._subparsers_map[subparser_key].print_help()
    else:
        parser.print_help()
    return


class Jet():
    def __init__(self, processed_args):
        self.processed_args = processed_args
        self.template_manager = TemplateManager(templates_dir=JET_HOME / "templates")
        
        # Load kubeconfig and namespace once at initialization
        self.kubeconfig = get_kubeconfig()
        self.namespace = get_current_namespace(self.kubeconfig)
        
        # Compute effective namespace (from args or kubectl context)
        if hasattr(processed_args, 'metadata') and processed_args.metadata.namespace:
            self.set_namespace = processed_args.metadata.namespace
        elif isinstance(processed_args, dict) and processed_args.get('namespace'):
            self.set_namespace = processed_args.get('namespace')
        else:
            self.set_namespace = self.namespace

    def launch_job(self):
        job_config_obj = self.processed_args
        
        # Set namespace from args or kubectl context
        job_config_obj.metadata.namespace = self.set_namespace
        
        if job_config_obj.save_template:
            self.template_manager.save_job_template(
                job_config=job_config_obj.to_dict(),
                job_name=job_config_obj.metadata.name,
                job_type='job',
                verbose=job_config_obj.verbose
            )
            return

        # Submit the job
        submit_job(
            job_config=job_config_obj.to_dict(),
            dry_run=job_config_obj.dry_run,
            verbose=job_config_obj.verbose
        )

        # Return if dry run
        if job_config_obj.dry_run:
            return

        # TODO: If follow is True, implement logic to follow job logs, status and events in addition to below pod log streaming.
        if job_config_obj.follow:
            namespace = self.set_namespace
            
            # Wait for job pods to be running
            print("Waiting for job pods to be ready...")
            pod_name = wait_for_job_pods_ready(
                            job_name=job_config_obj.metadata.name,
                            namespace=namespace,
                            timeout=300
                        )

            print(f"Job pod \x1b[1;38;2;30;144;255m{pod_name}\x1b[0m is running\n")

            print(f"Streaming logs from pod \x1b[1;38;2;30;144;255m{pod_name}\x1b[0m. Use Control-C to stop streaming.\n")

            # Stream logs from all pods
            get_logs(
                pod_name=pod_name,
                namespace=namespace,
                follow=True,
                timeout=None
            )

    def launch_jupyter(self):
        job_config_obj = self.processed_args
        
        # Set namespace from args or kubectl context
        job_config_obj.metadata.namespace = self.set_namespace
        
        pod_port = [item for item in job_config_obj.ports if item['name'] == 'jupyter'][0]['container_port']
        host_port = [item for item in job_config_obj.ports if item['name'] == 'jupyter'][0]['host_port']

        if job_config_obj.save_template:
            self.template_manager.save_job_template(
                job_config=job_config_obj.to_dict(),
                job_name=job_config_obj.metadata.name,
                job_type='jupyter',
                verbose=job_config_obj.verbose
            )
            return

        # Submit the job
        submit_job(
            job_config=job_config_obj.to_dict(),
            dry_run=job_config_obj.dry_run,
            verbose=job_config_obj.verbose
        )

        # Return if dry run
        if job_config_obj.dry_run:
            return

        # TODO: Watch for job and pod status. If any of them fail or deleted EXTERNALLY, stop port forwarding and exit gracefully.
        # TODO: If follow is True, implement logic to follow job logs, status and events in addition to below pod log streaming.
        # BUG: If a job is already finished, but resubmitted with the same name, kubectl will say "configured", which is not an error. So this impl goes on to wait for pod readiness, which will timeout and delete the job. Need to handle that better.

        namespace = self.set_namespace
        
        try:
            port_forwarder = None
            
            # Wait for Jupyter pod to be running
            print("Waiting for Jupyter pod to be ready...")
            jupyter_pod_name = wait_for_job_pods_ready(
                                job_name=job_config_obj.metadata.name,
                                namespace=namespace,
                                timeout=300
                            )
            print(f"Jupyter pod \x1b[1;38;2;30;144;255m{jupyter_pod_name}\x1b[0m is running\n")

            # Forward port from host to pod
            pod = init_pod_object(resource=jupyter_pod_name, namespace=namespace)
            port_forwarder = pod.portforward(remote_port=pod_port, local_port=host_port)
            port_forwarder.start()
            print(f"Forwarding from local port {host_port} to pod {jupyter_pod_name} port {pod_port}\n")

            # Stream Jupyter logs
            get_logs(
                pod_name=jupyter_pod_name,
                namespace=namespace,
                follow=True,
                timeout=None if job_config_obj.follow else 15 # No timeout for follow, 15 seconds for non-follow to capture token
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
            if port_forwarder is not None:
                port_forwarder.stop()
            try:
                delete_resource(
                    name=job_config_obj.metadata.name,
                    resource_type='job',
                    namespace=namespace
                )
            except Exception as delete_exception:

                print(f"Error deleting Jupyter job/pod: {delete_exception}")

        except Exception as e:
            # Delete jupyter job/pod if created
            print(f"Error occurred during jupyter server creation or running it: {e}. \n\nDeleting Jupyter job/pod if created")
            
            if port_forwarder is not None:
                port_forwarder.stop()

            # Block interrupts while cleaning up.
            # NOTE: For robustness, reset signal handler after cleanup.
            signal.signal(signal.SIGINT, signal.SIG_IGN)

            try:
                delete_resource(
                    name=job_config_obj.metadata.name,
                    resource_type='job',
                    namespace=namespace
                )
            except Exception as delete_exception:
                print(f"Error deleting Jupyter job/pod: {delete_exception}")
            raise e

    def launch_debug(self):
        job_config_obj = self.processed_args

        # Set namespace from args or kubectl context
        job_config_obj.metadata.namespace = self.set_namespace

        if job_config_obj.save_template:
            self.template_manager.save_job_template(
                job_config=job_config_obj.to_dict(),
                job_name=job_config_obj.metadata.name,
                job_type='debug',
                verbose=job_config_obj.verbose
            )
            return

        # Submit the job
        submit_job(
            job_config=job_config_obj.to_dict(),
            dry_run=job_config_obj.dry_run,
            verbose=job_config_obj.verbose
        )

        # Return if dry run
        if job_config_obj.dry_run:
            return

        # TODO: If follow is True, implement logic to follow job logs, status and events.
        # TODO: Exec only if a connect argument is passed. Yet to implement.

        namespace = self.set_namespace
        
        try:
            # Wait for debug pod to be running
            print("Waiting for debug pod to be ready...")
            debug_pod_name = wait_for_job_pods_ready(
                                job_name=job_config_obj.metadata.name,
                                namespace=namespace,
                                timeout=300
                            )
            print(f"Debug pod \x1b[1;38;2;30;144;255m{debug_pod_name}\x1b[0m is running\n")

            # Exec into the debug pod with the specified shell
            print(f"Connecting to debug pod \x1b[1;38;2;30;144;255m{debug_pod_name}\x1b[0m. Use \x1b[1;33mexit\x1b[0m to terminate the session and delete the debug job.\n")
            exec_into_pod(
                pod_name=debug_pod_name,
                namespace=namespace,
                shell=job_config_obj.spec.template_spec.containers[0].command.split(' ')[0] # Extract shell from command
            )

            # After exiting the exec session, delete the debug job/pod
            print("\nDebug session ended. Deleting debug job/pod...")
            delete_resource(
                name=job_config_obj.metadata.name,
                resource_type='job',
                namespace=namespace
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
                name=job_config_obj.metadata.name,
                resource_type='job',
                namespace=namespace
            )

        except Exception as e:
            print(f"Error occurred during creation or running of debug session: {e}. \n\nDeleting debug job/pod if created")

            # Block interrupts while cleaning up.
            # NOTE: For robustness, reset signal handler after cleanup.
            signal.signal(signal.SIGINT, signal.SIG_IGN)

            delete_resource(
                name=job_config_obj.metadata.name,
                resource_type='job',
                namespace=namespace
            )

    def list_templates(self):
        self.template_manager.print_templates(
            job_type=self.processed_args['job_type'],
            verbose=self.processed_args['verbose'],
            filter_by=self.processed_args['name_match_substr'],
            filter_regex=self.processed_args['regex'],
            sort_by=self.processed_args['sort_by']
        )

    def list_jobs(self):
        """Launch TUI to list and browse jobs."""
        result = run_tui(mode="jobs", namespace=self.set_namespace, mouse=False)

    def list_pods(self):
        """Launch TUI to list and browse pods."""
        result = run_tui(mode="pods", namespace=self.set_namespace, mouse=False, job_name=None)

    def get_logs(self):
        """Get logs from a job or pod."""
        resource_type = self.processed_args.get('resource_type')
        name = self.processed_args.get('name')
        kubectl_args = self.processed_args.get('kubectl_args', [])
        
        # Build kubectl logs command
        if resource_type == 'job':
            cmd = ['kubectl', 'logs', f'job/{name}', '-n', self.set_namespace] + kubectl_args
        else:
            cmd = ['kubectl', 'logs', name, '-n', self.set_namespace] + kubectl_args
        
        try:
            subprocess.run(cmd, check=False)
        except Exception as e:
            print(f"Error getting logs: {e}")

    def describe(self):
        """Use kubectl to describe a resource"""
        resource_type = self.processed_args.get('resource_type')
        name = self.processed_args.get('name')
        namespace = self.processed_args.get('namespace') or self.set_namespace
        kubectl_args = self.processed_args.get('kubectl_args', [])
        
        # Build kubectl describe command
        cmd = ['kubectl', 'describe', resource_type, name, '-n', namespace] + kubectl_args
        
        try:
            subprocess.run(cmd, check=False)
        except Exception as e:
            print(f"Error executing describe: {e}")

    def connect(self):
        """Connect (exec) into a pod."""
        resource_type = self.processed_args.get('resource_type')
        name = self.processed_args.get('name')
        
        if resource_type == 'pod' and name:
            shell_type = detect_shell(name, self.set_namespace)
            exec_into_pod(name, self.set_namespace, shell_type)
        elif resource_type == 'job' and name:
            # For jobs, show TUI to select a pod
            from .tui.k8s import K8sClient
            k8s = K8sClient(namespace=self.set_namespace)
            pods = k8s.get_pods(namespace=self.set_namespace, job_name=name)
            if pods:
                if len(pods) == 1:
                    # Only one pod, exec into it directly
                    pod_name = pods[0].name
                    shell_type = detect_shell(pod_name, self.set_namespace)
                    exec_into_pod(pod_name, self.set_namespace, shell_type)
                else:
                    # Launch TUI to select pod
                    result = run_tui(mode="pods", namespace=self.set_namespace, job_name=name)
                    if result and isinstance(result, tuple):
                        action, pod_name, ns = result
                        if action == "exec":
                            self._exec_into_pod(pod_name, ns)
            else:
                print(f"No pods found for job {name}")
        else:
            run_tui(mode="jobs", namespace=self.set_namespace)

    def delete(self):
        """Delete a resource."""
        resource_type = self.processed_args.get('resource_type')
        name = self.processed_args.get('name')
        kubectl_args = self.processed_args.get('kubectl_args', [])
        
        delete_resource(name=name, resource_type=resource_type, namespace=self.set_namespace, kubectl_args=kubectl_args)

def run(args, command, subcommand=None):
    # Jet instance
    jet = Jet(processed_args=args)

    # Execute commands
    if command == 'launch':
        if subcommand == 'job':
            jet.launch_job()
        elif subcommand == 'jupyter':
            jet.launch_jupyter()
        elif subcommand == 'debug':
            jet.launch_debug()
    elif command == 'list':
        if subcommand in ['templates', 'template', 'te', 't']:
            jet.list_templates()
        elif subcommand in ['jobs', 'job', 'jo', 'j']:
            jet.list_jobs()
        elif subcommand in ['pods', 'pod', 'po', 'p']:
            jet.list_pods()
        else:
            jet.list_jobs()  # Default to listing jobs
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
    parser, args = parse_arguments()

    # Handle case when no command is provided
    if args.jet_command is None:
        return print_help_and_exit(parser)

    # Handle case when 'launch' is provided but no subcommand (job/jupyter/debug)
    if args.jet_command == 'launch' and (not hasattr(args, 'launch_type') or args.launch_type is None):
        return print_help_and_exit(parser, 'launch')

    # Handle case when 'launch job/jupyter/debug' is provided but no name
    if args.jet_command == 'launch' and args.launch_type in ['job', 'jupyter', 'debug']:
        if not hasattr(args, 'name') or args.name is None:
            return print_help_and_exit(parser, f'launch_{args.launch_type}')

    # Handle case when 'logs' is provided but no arguments
    if args.jet_command == 'logs' and (not hasattr(args, 'logs_args') or not args.logs_args):
        return print_help_and_exit(parser, 'logs')

    # Handle case when 'connect' is provided but no arguments
    if args.jet_command == 'connect' and (not hasattr(args, 'connect_args') or not args.connect_args):
        return print_help_and_exit(parser, 'connect')

    # Handle case when 'delete' is provided but no arguments
    if args.jet_command == 'delete' and (not hasattr(args, 'delete_args') or not args.delete_args):
        return print_help_and_exit(parser, 'delete')

    # Handle case when 'describe' is provided but insufficient arguments (need resource_type and name)
    if args.jet_command == 'describe':
        describe_args = args.describe_args if hasattr(args, 'describe_args') else []
        # Filter out namespace flags to count actual positional args
        positional_args = []
        i = 0
        while i < len(describe_args):
            if describe_args[i] in ['-n', '--namespace'] and i + 1 < len(describe_args):
                i += 2  # Skip flag and value
            elif describe_args[i].startswith('--namespace='):
                i += 1  # Skip flag
            elif describe_args[i].startswith('-'):
                i += 1  # Skip other flags
            else:
                positional_args.append(describe_args[i])
                i += 1
        # Need at least 2 positional args: resource_type and name
        if len(positional_args) < 2:
            return print_help_and_exit(parser, 'describe')

    # Process arguments
    processor = ProcessArguments(args)
    processed_args = processor.process()

    # Run Jet commands
    subcommand = None
    if hasattr(args, 'launch_type'):
        subcommand = args.launch_type
    elif hasattr(args, 'list_type'):
        subcommand = args.list_type
    
    run(processed_args, args.jet_command, subcommand)

if __name__ == "__main__":
    cli()