"""MediaVault exception hierarchy (NFR-004)."""


class MediaVaultError(Exception):
    """Base class for all MediaVault-specific errors."""


class ConfigurationError(MediaVaultError):
    """Invalid or unreadable configuration (FR-1208)."""


class PathValidationError(MediaVaultError):
    """A supplied path failed validation (FR-300–FR-304)."""


class LockError(MediaVaultError):
    """Another scan holds the lock (NFR-008)."""


class MigrationError(MediaVaultError):
    """A schema migration failed or the DB is from the future (FR-802a)."""
