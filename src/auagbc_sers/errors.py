"""Domain-specific exceptions with user-actionable messages."""


class RamanPipelineError(RuntimeError):
    """Base class for expected pipeline failures."""


class ConfigurationError(RamanPipelineError):
    """The manifest or processing configuration is incomplete or inconsistent."""


class ImportFormatError(RamanPipelineError):
    """A spectrum file cannot be interpreted without guessing."""


class ProcessingError(RamanPipelineError):
    """A numerical processing step cannot be applied safely."""


class VerificationError(RamanPipelineError):
    """A recorded checksum or provenance assertion does not hold."""
