"""
PrivacyShieldAI - Groq Cloud LLM Provider
Production-grade provider implementation for Groq Cloud API with SDK & HTTP failovers.
"""

import os
import time
import logging
from typing import Optional, List, Dict, Any, Tuple

try:
    from groq import Groq
    HAS_GROQ_SDK = True
except ImportError:
    Groq = None
    HAS_GROQ_SDK = False

from app.agents.llm_providers.base import (
    BaseLLMProvider,
    LLMProviderResponse,
    LLMAuthenticationError,
    LLMForbiddenError,
    LLMQuotaOrRateLimitError,
    LLMInvalidModelError,
    LLMTimeoutError,
    LLMConnectionError,
    LLMServerError,
    LLMRouterException,
)

logger = logging.getLogger(__name__)

# Standard Groq model aliases & normalization mapping
GROQ_MODEL_MAPPING = {
    "llama3-70b-8192": "llama-3.3-70b-versatile",
    "llama3-8b-8192": "llama-3.1-8b-instant",
    "mixtral-8x7b-32768": "llama-3.1-8b-instant",
    "gemma2-9b-it": "llama-3.1-8b-instant",
    "llama-3.3-70b-versatile": "llama-3.3-70b-versatile",
    "llama-3.3-70b": "llama-3.3-70b-versatile",
    "llama-3.3-70b-instruct": "llama-3.3-70b-versatile",
    "llama-3.3-70b-v": "llama-3.3-70b-versatile",
    "llama-3.3-70b": "llama-3.3-70b-versatile",
    "llama-3-70b-privacyguard": "llama-3.3-70b-versatile",
    "llama-3.3-70b": "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant": "llama-3.1-8b-instant",
    "llama-3.1-8b": "llama-3.1-8b-instant",
    "llama-3.1-70b-versatile": "llama-3.3-70b-versatile",
}


def normalize_groq_model(model_name: Optional[str]) -> str:
    """Normalizes model aliases and case variations for Groq API."""
    if not model_name:
        return "llama-3.3-70b-versatile"
    
    clean = model_name.strip()
    lower = clean.lower()

    if lower in GROQ_MODEL_MAPPING:
        return GROQ_MODEL_MAPPING[lower]
    
    # Check partial matches
    if "70b" in lower and ("llama" in lower or "llama3" in lower):
        return "llama-3.3-70b-versatile"
    if "8b" in lower and ("llama" in lower or "llama3" in lower):
        return "llama-3.1-8b-instant"

    return clean


class GroqProvider(BaseLLMProvider):
    """Groq Cloud API LLM Provider."""

    def __init__(self, api_key: Optional[str] = None, default_model: str = "llama-3.3-70b-versatile"):
        key = api_key or os.getenv("GROQ_API_KEY", "")
        super().__init__(provider_name="Groq", default_model=default_model, api_key=key)

    def validate_config(self, model_name: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        """Validates API key and model name for Groq."""
        key = (self.api_key or "").strip()
        if not key:
            return False, "Groq API key is missing or empty."
        if len(key) < 15 or not key.startswith("gsk_"):
            return False, "Groq API key format invalid (must start with 'gsk_')."

        target_model = normalize_groq_model(model_name or self.default_model)
        if not target_model:
            return False, "Target model name is empty or invalid."

        return True, None

    def health_check(self) -> Dict[str, Any]:
        """Runs a lightweight health check on Groq API."""
        is_valid, err_reason = self.validate_config()
        if not is_valid:
            return {
                "status": "Error",
                "provider": "Groq",
                "message": err_reason,
                "api_key_present": bool(self.api_key and len(self.api_key.strip()) > 0),
            }

        start_t = time.time()
        try:
            import httpx
            resp = httpx.get(
                "https://api.groq.com/openai/v1/models",
                headers={"Authorization": f"Bearer {self.api_key.strip()}"},
                timeout=5.0
            )
            latency = int((time.time() - start_t) * 1000)

            if resp.status_code == 200:
                return {
                    "status": "Healthy",
                    "provider": "Groq",
                    "latency_ms": latency,
                    "default_model": self.default_model,
                    "api_key_present": True
                }
            elif resp.status_code == 401:
                return {
                    "status": "Error",
                    "provider": "Groq",
                    "message": "401 Unauthorized - Invalid Groq API Key.",
                    "api_key_present": True
                }
            else:
                return {
                    "status": "Warning",
                    "provider": "Groq",
                    "message": f"Groq HTTP status {resp.status_code}: {resp.text[:100]}",
                    "api_key_present": True
                }
        except Exception as e:
            return {
                "status": "Error",
                "provider": "Groq",
                "message": f"Health check failed: {str(e)}",
                "api_key_present": True
            }

    def generate(
        self,
        messages: List[Dict[str, str]],
        model_name: Optional[str] = None,
        temperature: float = 0.15,
        max_tokens: int = 2048,
        top_p: float = 0.9,
        **kwargs
    ) -> LLMProviderResponse:
        """Executes LLM generation via Groq SDK or HTTP API with structured error handling & 8B instant fallback on 429."""
        target_model = normalize_groq_model(model_name or self.default_model)
        try:
            return self._single_generate(messages, target_model, temperature, max_tokens, top_p, **kwargs)
        except LLMQuotaOrRateLimitError as e:
            if target_model != "llama-3.1-8b-instant":
                logger.info(f"[GroqProvider] Model '{target_model}' hit 429 Rate Limit. Attempting auto-switch to 'llama-3.1-8b-instant'...")
                try:
                    return self._single_generate(messages, "llama-3.1-8b-instant", temperature, max_tokens, top_p, **kwargs)
                except Exception:
                    pass
            raise e

    def _single_generate(
        self,
        messages: List[Dict[str, str]],
        target_model: str,
        temperature: float = 0.15,
        max_tokens: int = 2048,
        top_p: float = 0.9,
        **kwargs
    ) -> LLMProviderResponse:
        """Executes single generation attempt for target model."""
        start_t = time.time()
        clean_key = (self.api_key or "").strip()

        is_valid, val_err = self.validate_config(target_model)
        if not is_valid:
            raise LLMAuthenticationError(
                message=val_err or "Groq configuration validation failed",
                provider="Groq"
            )

        last_exception: Optional[Exception] = None

        # 1. Try official Groq SDK
        if HAS_GROQ_SDK:
            try:
                client = Groq(api_key=clean_key)
                completion = client.chat.completions.create(
                    model=target_model,
                    messages=messages,
                    temperature=max(0.01, min(float(temperature), 1.0)),
                    max_tokens=int(max_tokens),
                    top_p=float(top_p)
                )
                latency_ms = int((time.time() - start_t) * 1000)

                if completion and completion.choices and completion.choices[0].message:
                    content = completion.choices[0].message.content
                    if content and content.strip():
                        return LLMProviderResponse(
                            content=content.strip(),
                            model_name=target_model,
                            provider_name="Groq",
                            routing_strategy="Cloud",
                            raw_response=completion,
                            latency_ms=latency_ms
                        )
            except Exception as e:
                err_msg = str(e)
                logger.warning(f"[GroqProvider] SDK call failed ({err_msg}). Attempting HTTP fallback.")
                if "401" in err_msg or "invalid_api_key" in err_msg.lower() or "unauthorized" in err_msg.lower():
                    last_exception = LLMAuthenticationError(f"401 Unauthorized - {err_msg}", provider="Groq", status_code=401)
                elif "403" in err_msg or "forbidden" in err_msg.lower():
                    last_exception = LLMForbiddenError(f"403 Forbidden - {err_msg}", provider="Groq", status_code=403)
                elif "429" in err_msg or "rate_limit" in err_msg.lower() or "quota" in err_msg.lower():
                    last_exception = LLMQuotaOrRateLimitError(f"429 Rate Limit Exceeded - {err_msg}", provider="Groq", status_code=429)
                elif "404" in err_msg or "model_not_found" in err_msg.lower():
                    last_exception = LLMInvalidModelError(f"404 Invalid Model '{target_model}' - {err_msg}", provider="Groq", status_code=404)
                elif "timeout" in err_msg.lower():
                    last_exception = LLMTimeoutError(f"Groq API Timeout - {err_msg}", provider="Groq")
                else:
                    last_exception = LLMRouterException(f"Groq SDK Error - {err_msg}", provider="Groq")

        # 2. Try HTTP API Fallback
        try:
            import httpx

            payload = {
                "model": target_model,
                "messages": messages,
                "temperature": max(0.01, min(float(temperature), 1.0)),
                "max_tokens": int(max_tokens),
                "top_p": float(top_p)
            }

            resp = httpx.post(
                "https://api.groq.com/openai/v1/chat/completions",
                json=payload,
                headers={
                    "Authorization": f"Bearer {clean_key}",
                    "Content-Type": "application/json"
                },
                timeout=25.0
            )

            latency_ms = int((time.time() - start_t) * 1000)

            if resp.status_code == 200:
                body = resp.json()
                content = body["choices"][0]["message"]["content"].strip()
                if content:
                    return LLMProviderResponse(
                        content=content,
                        model_name=target_model,
                        provider_name="Groq",
                        routing_strategy="Cloud",
                        raw_response=body,
                        latency_ms=latency_ms
                    )
            elif resp.status_code == 401:
                raise LLMAuthenticationError("401 Unauthorized - Invalid Groq API Key", provider="Groq", status_code=401)
            elif resp.status_code == 403:
                raise LLMForbiddenError("403 Forbidden - Access denied", provider="Groq", status_code=403)
            elif resp.status_code == 429:
                raise LLMQuotaOrRateLimitError("429 Rate Limit Exceeded", provider="Groq", status_code=429)
            elif resp.status_code in (400, 404):
                raise LLMInvalidModelError(f"{resp.status_code} Invalid Model '{target_model}': {resp.text[:150]}", provider="Groq", status_code=resp.status_code)
            elif resp.status_code >= 500:
                raise LLMServerError(f"{resp.status_code} Groq Server Error: {resp.text[:150]}", provider="Groq", status_code=resp.status_code)
            else:
                raise LLMRouterException(f"HTTP Error {resp.status_code}: {resp.text[:150]}", provider="Groq", status_code=resp.status_code)

        except (httpx.TimeoutException, TimeoutError) as e:
            raise LLMTimeoutError(f"Groq HTTP request timed out after 25s: {str(e)}", provider="Groq") from e
        except (httpx.ConnectError, httpx.NetworkError) as e:
            raise LLMConnectionError(f"Groq network connection failed: {str(e)}", provider="Groq") from e
        except LLMRouterException:
            raise
        except Exception as e:
            if last_exception and isinstance(last_exception, LLMRouterException):
                raise last_exception
            raise LLMRouterException(f"Groq call failed: {str(e)}", provider="Groq") from e

    def generate_stream(
        self,
        messages: List[Dict[str, str]],
        model_name: Optional[str] = None,
        temperature: float = 0.15,
        max_tokens: int = 1024,
        top_p: float = 0.9,
        **kwargs
    ) -> Tuple[Any, str]:
        """Returns streaming response from Groq SDK."""
        target_model = normalize_groq_model(model_name or self.default_model)
        clean_key = (self.api_key or "").strip()

        is_valid, val_err = self.validate_config(target_model)
        if not is_valid:
            raise LLMAuthenticationError(val_err or "Groq API key missing", provider="Groq")

        if not HAS_GROQ_SDK:
            raise RuntimeError("Groq SDK is not installed. Please install groq to enable streaming.")

        client = Groq(api_key=clean_key)
        stream = client.chat.completions.create(
            model=target_model,
            messages=messages,
            temperature=float(temperature),
            max_tokens=int(max_tokens),
            top_p=float(top_p),
            stream=True
        )
        return stream, target_model
