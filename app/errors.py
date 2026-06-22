class RuntimeConfigurationError(RuntimeError):
    """Raised when production starts with an unsafe provider configuration."""


class LLMProviderError(RuntimeError):
    """Raised when a production LLM request cannot produce a real response."""


class SearchProviderError(RuntimeError):
    """Raised when production search cannot return real source material."""
