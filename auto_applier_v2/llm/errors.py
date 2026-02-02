class LLMError(Exception):
    """Base error for LLM operations."""


class LLMTimeoutError(LLMError):
    """Raised when the LLM request times out."""


class LLMAuthError(LLMError):
    """Raised when the LLM provider rejects authentication."""


class LLMProviderError(LLMError):
    """Raised for provider-side or network errors."""


class LLMParseError(LLMError):
    """Raised when the LLM response cannot be parsed."""
