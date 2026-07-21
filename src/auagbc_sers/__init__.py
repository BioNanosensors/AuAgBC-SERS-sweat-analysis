"""Auditable Raman/SERS processing tools."""

__version__ = "0.1.0"

from .errors import ConfigurationError, ImportFormatError, ProcessingError, VerificationError
from .io import inspect_spectrum_file, read_spectrum_file
from .pipeline import process_job, verify_run
from .profiles import PROFILE_NAMES, get_profile

__all__ = [
    "ConfigurationError",
    "ImportFormatError",
    "ProcessingError",
    "VerificationError",
    "PROFILE_NAMES",
    "get_profile",
    "inspect_spectrum_file",
    "read_spectrum_file",
    "process_job",
    "verify_run",
]
