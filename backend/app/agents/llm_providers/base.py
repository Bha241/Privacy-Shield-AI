"""
PrivacyShieldAI - LLM Provider Base & Exceptions
Abstract base class and structured exception hierarchy for production-grade LLM provider abstraction.
"""

import time
import uuid
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple, Generator

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Structured Exception Hierarchy
# -----------------------------------------------------------------------------

class LLMRouterException(Exception):
    """Base exception for LLM Router errors."""
    def __init__(self, message: str, provider: str = "Unknown", status_code: Optional[int] = None, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.provider = provider
        self.status_code = status_code
        self.details = details or {}


class LLMAuthenticationError(LLMRouterException):
    """401 Unauthorized or Invalid API key errors."""
    pass


class LLMForbiddenError(LLMRouterException):
    """403 Forbidden or Access Denied errors."""
    pass


class LLMQuotaOrRateLimitError(LLMRouterException):
    """429 Rate Limit Exceeded or Quota Exhausted errors."""
    pass


class LLMInvalidModelError(LLMRouterException):
    """400/404 Model Not Found or Invalid Model errors."""
    pass


class LLMTimeoutError(LLMRouterException):
    """Network request or gateway timeout errors."""
    pass


class LLMConnectionError(LLMRouterException):
    """Network connection, DNS, or socket failure errors."""
    pass


class LLMServerError(LLMRouterException):
    """500/502/503 Internal Server Error from LLM API."""
    pass


# -----------------------------------------------------------------------------
# Standardized Provider Response Dataclass
# -----------------------------------------------------------------------------

@dataclass
class LLMProviderResponse:
    content: str
    model_name: str
    provider_name: str
    routing_strategy: str = "Cloud"  # "Cloud" or "Fallback"
    fallback_reason: Optional[str] = None
    finish_reason: str = "stop"
    raw_response: Optional[Any] = None
    latency_ms: int = 0
    request_id: str = field(default_factory=lambda: f"req-{uuid.uuid4().hex[:12]}")
    error_note: Optional[str] = None

    @property
    def engine_used(self) -> str:
        """Backward-compatible engine_used string description."""
        if self.routing_strategy == "Fallback" and self.fallback_reason:
            return f"{self.provider_name} Engine (Fallback: {self.fallback_reason})"
        return f"{self.provider_name} Cloud API ({self.model_name})"


# -----------------------------------------------------------------------------
# Base LLM Provider Interface
# -----------------------------------------------------------------------------

class BaseLLMProvider(ABC):
    """Abstract Base Class for all LLM Providers."""

    def __init__(self, provider_name: str, default_model: str, api_key: Optional[str] = None):
        self.provider_name = provider_name
        self.default_model = default_model
        self.api_key = api_key or ""

    @abstractmethod
    def validate_config(self, model_name: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        """
        Validates API key existence, non-emptiness, and model name validity.
        Returns (is_valid, error_reason).
        """
        pass

    @abstractmethod
    def health_check(self) -> Dict[str, Any]:
        """
        Runs a lightweight health check verifying endpoint reachability and credentials.
        Returns dict with status ("Healthy", "Warning", "Error") and details.
        """
        pass

    @abstractmethod
    def generate(
        self,
        messages: List[Dict[str, str]],
        model_name: Optional[str] = None,
        temperature: float = 0.15,
        max_tokens: int = 2048,
        top_p: float = 0.9,
        **kwargs
    ) -> LLMProviderResponse:
        """Generates chat completion response. Raises structured LLMRouterException on failure."""
        pass

    def generate_stream(
        self,
        messages: List[Dict[str, str]],
        model_name: Optional[str] = None,
        temperature: float = 0.15,
        max_tokens: int = 1024,
        top_p: float = 0.9,
        **kwargs
    ) -> Tuple[Any, str]:
        """Generates streaming completion stream. Returns (stream_generator, target_model)."""
        raise NotImplementedError(f"Streaming is not supported for provider '{self.provider_name}'.")
