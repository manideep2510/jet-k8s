"""
Re-exports configuration from the config module to load default values.

Default configuration is stored in ~/.local/share/jet/config.yaml (or $XDG_DATA_HOME/jet/config.yaml).
Use jet.config.get_config() for direct access to configuration management.
"""

from pathlib import Path
from .config import (
    JET_HOME,
    XDG_DATA_HOME,
    get_config,
)

# Load configuration
_config = get_config()

DEFAULT_CPU = _config.get('cpu')
DEFAULT_MEMORY = _config.get('memory')
DEFAULT_SCHEDULER = _config.get('scheduler')
DEFAULT_PRIORITY = _config.get('priority')
DEFAULT_RESTART_POLICY = _config.get('restart_policy')
DEFAULT_JUPYTER_PORT = _config.get('jupyter_port')
DEFAULT_BACKOFF_LIMIT = _config.get('backoff_limit')
DEFAULT_JOB_TTL_SECONDS_AFTER_FINISHED = _config.get('job_ttl_seconds_after_finished')
DEFAULT_JUPYTER_TTL_SECONDS_AFTER_FINISHED = _config.get('jupyter_ttl_seconds_after_finished')
DEFAULT_DEBUG_TTL_SECONDS_AFTER_FINISHED = _config.get('debug_ttl_seconds_after_finished')
DEFAULT_DEBUG_JOB_DURATION_SECONDS = _config.get('debug_job_duration_seconds')
JUPYTER_HOME_BASE = _config.get('jupyter_home_base')
DEFAULT_JOB_POD_WAITING_TIMEOUT = _config.get('job_pod_waiting_timeout')
DEFAULT_SHELL = _config.get('shell')