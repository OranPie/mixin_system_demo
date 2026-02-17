class MixinSystemError(Exception):
    """Base error."""

class MixinConflictError(MixinSystemError):
    """Raised when injectors conflict under the configured policy."""

class MixinMatchError(MixinSystemError):
    """Raised when require/expect match constraints fail."""
