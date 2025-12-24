"""
Configuration management for Jet.

This module handles loading and saving configuration from a YAML file stored in JET_HOME.
It provides default values and allows users to customize settings via the config file.
"""

import os
from pathlib import Path
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap
import logging

# Base paths (these are not configurable via config file)
XDG_DATA_HOME = os.getenv("XDG_DATA_HOME", Path.home() / ".local" / "share")
JET_HOME = Path(XDG_DATA_HOME) / "jet"
CONFIG_FILE = JET_HOME / "config.yaml"

# Initialize ruamel.yaml with round-trip mode to preserve comments
yaml = YAML()
yaml.preserve_quotes = True
yaml.indent(mapping=2, sequence=4, offset=2)

# Default configuration values
DEFAULT_CONFIG = {
    'cpu': '1:1',
    'memory': '4Gi:4Gi',
    'scheduler': None,
    'priority': None,
    'restart_policy': 'Never',
    'jupyter_port': '8888',
    'backoff_limit': None,
    'job_ttl_seconds_after_finished': 1296000,
    'jupyter_ttl_seconds_after_finished': 1296000,
    'debug_ttl_seconds_after_finished': 21600,
    'debug_job_duration_seconds': 21600,
    'jupyter_home_base': str(XDG_DATA_HOME),
    'job_pod_waiting_timeout': 300,
    'shell': '/bin/bash'
}

# Comments for each configuration key
CONFIG_COMMENTS = {
    '_header': [
        'Jet Configuration File',
        '======================',
        'This file contains default settings for Jet CLI.',
        'Modify values below to customize your defaults.',
        "Run 'jet launch job --help' for more details on each option.",
        '',
    ],
    'cpu': 'CPU request and limit in format "request:limit". Examples: "1:1", "500m:2", "0.5:1"',
    'memory': 'Memory request and limit in format "request:limit". Examples: "4Gi:4Gi", "512Mi:2Gi"',
    'scheduler': 'Kubernetes scheduler name (null uses the default scheduler). Examples: "volcano", "kueue"',
    'priority': 'Priority class name for jobs (null means no priority class). Must match a PriorityClass in your cluster',
    'restart_policy': 'Pod restart policy: "Never", "OnFailure", or "Always"',
    'jupyter_port': 'Jupyter server port inside the container',
    'backoff_limit': 'Number of retries before marking a job as failed (Default: null = Kubernetes default of 6)',
    'job_ttl_seconds_after_finished': 'Seconds after job completion before auto-deletion (Default: 1296000 = 15 days)',
    'jupyter_ttl_seconds_after_finished': 'Seconds after Jupyter job completion before auto-deletion (Default: 1296000 = 15 days)',
    'debug_ttl_seconds_after_finished': 'Seconds after debug job completion before auto-deletion (Default: 21600 = 6 hours)',
    'debug_job_duration_seconds': 'Duration for debug sessions in seconds (Default: 21600 = 6 hours)',
    'jupyter_home_base': 'Base path for Jupyter home directory (where .local, .jupyter, .ipython are stored)',
    'job_pod_waiting_timeout': 'Timeout in seconds to wait for job pod to start running before considering it failed (Default: 300 seconds)',
    'shell': 'Default shell to use in debug sessions (e.g., /bin/bash, /bin/zsh, Default: /bin/bash)',
}


def _create_commented_config():
    """Create a CommentedMap with all configuration values and comments."""
    config = CommentedMap()
    
    # Add header comments
    header_lines = CONFIG_COMMENTS['_header']
    config.yaml_set_start_comment('\n'.join(header_lines))
    
    # Add each config value with its comment
    for key, value in DEFAULT_CONFIG.items():
        config[key] = value
        if key in CONFIG_COMMENTS:
            config.yaml_set_comment_before_after_key(key, before="\n"+CONFIG_COMMENTS[key])
    
    return config


class Config:
    """Configuration manager for Jet."""
    
    _instance = None
    _config = None
    _commented_config = None  # Preserve comments for saving
    
    def __new__(cls):
        """Singleton pattern to ensure only one config instance exists."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_config()
        return cls._instance
    
    def _ensure_jet_home(self):
        """Ensure JET_HOME directory exists."""
        JET_HOME.mkdir(parents=True, exist_ok=True)
    
    def _load_config(self):
        """Load configuration from file or create with defaults."""
        self._ensure_jet_home()
        
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, 'r') as f:
                    self._commented_config = yaml.load(f)
                if self._commented_config is None:
                    self._commented_config = CommentedMap()
                # Merge with defaults (user config takes precedence)
                merged = DEFAULT_CONFIG.copy()
                merged.update(dict(self._commented_config))
                self._config = merged
            except Exception as e:
                logging.warning(f"Error loading config file: {e}. Using defaults.")
                self._config = DEFAULT_CONFIG.copy()
                self._commented_config = _create_commented_config()
        else:
            # Create default config file with comments
            self._config = DEFAULT_CONFIG.copy()
            self._commented_config = _create_commented_config()
            self._save_config()
    
    def _save_config(self):
        """Save current configuration to file, preserving comments."""
        self._ensure_jet_home()
        try:
            # Update the commented config with current values
            for key, value in self._config.items():
                self._commented_config[key] = value
            
            with open(CONFIG_FILE, 'w') as f:
                yaml.dump(self._commented_config, f)
        except Exception as e:
            logging.warning(f"Error saving config file: {e}")
    
    def get(self, key, default=None):
        """Get a configuration value."""
        return self._config.get(key, default)
    
    def set(self, key, value):
        """Set a configuration value and save to file."""
        self._config[key] = value
        self._save_config()
    
    def reload(self):
        """Reload configuration from file."""
        self._load_config()
    
    @property
    def all(self):
        """Return all configuration values."""
        return self._config.copy()

def get_config():
    """Get the global configuration instance."""
    return Config()
