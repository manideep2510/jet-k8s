try:
    from importlib.metadata import version, PackageNotFoundError
except ImportError:
    from importlib_metadata import version, PackageNotFoundError

# Version of the jet package
try:
    __version__ = version("jet-k8s")
except PackageNotFoundError:
    __version__ = "unknown"

from .jet import cli

__all__ = ["cli", "__version__"]
