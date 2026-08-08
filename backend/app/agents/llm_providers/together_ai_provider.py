"""
PrivacyShieldAI - Together AI Provider
Production-grade provider implementation for Together AI API.
"""

import os
import time
import logging
from typing import Optional, List, Dict, Any, Tuple

from app.agents.llm_providers.base import (
    BaseLLMProvider,
    LLMProviderResponse,
    LLMAuthenticationError,
    LLMQuotaOrRateLimitError,
    LLMTimeoutError,
    LLMConnectionError,
    LLMRouterException,
)

logger = logging.getLogger(__name__)


class TogetherAIProvider(BaseLLMProvider):
    """Together AI API Provider."""

    def __init__(self, api_key: Optional[str] = None, default_model: str = "meta-llama/Llama-3.3-70B-Instruct-Turbo"):
        key = api_key or os.getenv("TOGETHER_API_KEY", "")
        super().__init__(provider_name="Together AI", default_model=default_model, api_key=key)

    def validate_config(self, model_name: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        key = (self.api_key or "").strip()
        if not key:
            return False, "Together AI API key is missing or empty."
        return True, None

    def health_check(self) -> Dict[str, Any]:
        is_valid, err_reason = self.validate_config()
        if not is_valid:
            return {"status": "Error", "provider": "Together AI", "message": err_reason, "api_key_present": False}
        return {"status": "Healthy", "provider": "Together AI", "default_model": self.default_model, "api_key_present": True}

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
        target_model = model_name or self.default_model
        clean_key = (self.api_key or "").strip()

        is_valid, val_err = self.validate_config(target_model)
        if not is_valid:
            raise LLMAuthenticationError(val_err or "Together AI API key missing", provider="Together AI")

        try:
            import httpx
            resp = httpx.post(
                "https://api.together.xyz/v1/chat/completions",
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
                    provider_name="Together AI",
                    routing_strategy="Cloud",
                    raw_response=body,
                    latency_ms=latency_ms
                )
            elif resp.status_code == 401:
                raise LLMAuthenticationError("401 Unauthorized - Invalid Together API Key", provider="Together AI", status_code=401)
            elif resp.status_code == 429:
                raise LLMQuotaOrRateLimitError("429 Rate Limit Exceeded", provider="Together AI", status_code=429)
            else:
                raise LLMRouterException(f"Together AI Error {resp.status_code}: {resp.text[:150]}", provider="Together AI", status_code=resp.status_code)
        except (httpx.TimeoutException, TimeoutError) as e:
            raise LLMTimeoutError(f"Together AI API Timeout: {str(e)}", provider="Together AI") from e
        except (httpx.ConnectError, httpx.NetworkError) as e:
            raise LLMConnectionError(f"Together AI Connection Error: {str(e)}", provider="Together AI") from e
        except LLMRouterException:
            raise
        except Exception as e:
            raise LLMRouterException(f"Together AI generation failed: {str(e)}", provider="Together AI") from e
