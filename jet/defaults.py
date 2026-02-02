import os
from pathlib import Path

DEFAULT_CPU = None
DEFAULT_MEMORY = None
DEFAULT_SCHEDULER = None  # None uses Kubernetes default scheduler
DEFAULT_PRIORITY = None  # None means no priority class is set
DEFAULT_RESTART_POLICY = 'Never'
DEFAULT_JUPYTER_PORT = '8888'
DEFAULT_BACKOFF_LIMIT = None  # 6 retries by default
DEFAULT_JOB_TTL_SECONDS_AFTER_FINISHED = 1296000  # 15 days
DEFAULT_JUPYTER_TTL_SECONDS_AFTER_FINISHED = 1296000  # 15 days
DEFAULT_DEBUG_TTL_SECONDS_AFTER_FINISHED = 21600  # 6 hours
DEFAULT_DEBUG_JOB_DURATION_SECONDS = 21600  # 6 hours
# Timeout when waiting for job pods to start when `--follow` is used or when waiting for jupyter or debug pods to start
DEFAULT_JOB_POD_WAITING_TIMEOUT = 300  # 5 minutes

DEFAULT_SHELL = '/bin/bash'
DEFAULT_PATH = '/usr/local/cuda/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'

XDG_DATA_HOME = os.getenv("XDG_DATA_HOME", Path.home() / ".local" / "share")
JET_HOME = Path(XDG_DATA_HOME) / "jet"

XDG_CACHE_HOME = os.getenv("XDG_CACHE_HOME", Path.home() / ".cache")