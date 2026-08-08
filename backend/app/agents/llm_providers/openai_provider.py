"""
PrivacyShieldAI - OpenAI Provider
Production-grade provider implementation for OpenAI API.
"""

import os
import time
import logging
from typing import Optional, List, Dict, Any, Tuple

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


class OpenAIProvider(BaseLLMProvider):
    """OpenAI API Provider."""

    def __init__(self, api_key: Optional[str] = None, default_model: str = "gpt-4o"):
        key = api_key or os.getenv("OPENAI_API_KEY", "")
        super().__init__(provider_name="OpenAI", default_model=default_model, api_key=key)

    def validate_config(self, model_name: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        key = (self.api_key or "").strip()
        if not key:
            return False, "OpenAI API key is missing or empty."
        if not key.startswith("sk-"):
            return False, "OpenAI API key format invalid (must start with 'sk-')."
        return True, None

    def health_check(self) -> Dict[str, Any]:
        is_valid, err_reason = self.validate_config()
        if not is_valid:
            return {"status": "Error", "provider": "OpenAI", "message": err_reason, "api_key_present": False}

        start_t = time.time()
        try:
            import httpx
            resp = httpx.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {self.api_key.strip()}"},
                timeout=5.0
            )
            latency = int((time.time() - start_t) * 1000)
            if resp.status_code == 200:
                return {"status": "Healthy", "provider": "OpenAI", "latency_ms": latency, "default_model": self.default_model, "api_key_present": True}
            elif resp.status_code == 401:
                return {"status": "Error", "provider": "OpenAI", "message": "401 Unauthorized - Invalid OpenAI API Key.", "api_key_present": True}
            else:
                return {"status": "Warning", "provider": "OpenAI", "message": f"HTTP status {resp.status_code}", "api_key_present": True}
        except Exception as e:
            return {"status": "Error", "provider": "OpenAI", "message": f"Health check failed: {str(e)}", "api_key_present": True}

    def generate(
        self,
        messages: List[Dict[str, str]],
        model_name: Optional[str] = None,
        temperature: float = 0.15,
        max_tokens: int = 2048,
        top_p: float = 0.9,
        **kwargs
    ) -> LLMProviderResponse:
        start_t = time.time()
        target_model = (model_name or self.default_model).replace("openai/", "")
        clean_key = (self.api_key or "").strip()

        is_valid, val_err = self.validate_config(target_model)
        if not is_valid:
            raise LLMAuthenticationError(val_err or "OpenAI API key missing", provider="OpenAI")

        try:
            import httpx
            resp = httpx.post(
                "https://api.openai.com/v1/chat/completions",
                json={
                    "model": target_model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "top_p": top_p
                },
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
                return LLMProviderResponse(
                    content=content,
                    model_name=target_model,
                    provider_name="OpenAI",
                    routing_strategy="Cloud",
                    raw_response=body,
                    latency_ms=latency_ms
                )
            elif resp.status_code == 401:
                raise LLMAuthenticationError("401 Unauthorized - Invalid OpenAI API Key", provider="OpenAI", status_code=401)
            elif resp.status_code == 429:
                raise LLMQuotaOrRateLimitError("429 Rate Limit / Quota Exceeded", provider="OpenAI", status_code=429)
            else:
                raise LLMRouterException(f"OpenAI Error {resp.status_code}: {resp.text[:150]}", provider="OpenAI", status_code=resp.status_code)
        except (httpx.TimeoutException, TimeoutError) as e:
            raise LLMTimeoutError(f"OpenAI API Timeout: {str(e)}", provider="OpenAI") from e
        except (httpx.ConnectError, httpx.NetworkError) as e:
            raise LLMConnectionError(f"OpenAI Connection Error: {str(e)}", provider="OpenAI") from e
        except LLMRouterException:
            raise
        except Exception as e:
            raise LLMRouterException(f"OpenAI generation failed: {str(e)}", provider="OpenAI") from e
