"""Application-specific exceptions."""


class ScannerError(Exception):
    """Base class for scanner failures."""

    category = "scanner"


class ConfigurationError(ScannerError):
    """Configuration is missing or invalid."""

    category = "configuration"


class SymbolMasterValidationError(ConfigurationError):
    """Symbol-master CSV data is malformed or unusable."""

    category = "symbol_master_validation"


class ExtractionError(ScannerError):
    """Finviz page extraction failed."""

    category = "extraction"


class CaptchaError(ScannerError):
    """Finviz presented a CAPTCHA or login challenge."""

    category = "captcha"


class ValidationError(ScannerError):
    """Extracted data failed validation."""

    category = "validation"


class ExchangeResolutionError(ScannerError):
    """One or more symbols could not be safely exchange-qualified."""

    category = "exchange_resolution"

    def __init__(self, message: str, unresolved: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.unresolved = unresolved


class StorageError(ScannerError):
    """Snapshot or database persistence failed."""

    category = "storage"


class LockError(ScannerError):
    """Another scanner run is already active."""

    category = "lock"
