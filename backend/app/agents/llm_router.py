"""
PrivacyShieldAI - LLM Router Module
Centralized, deterministic LLM routing engine supporting multi-provider dispatch:
- Groq Cloud API (llama-3.3-70b-versatile, llama-3.1-8b-instant, etc.)
- Meta Llama API
- OpenAI (gpt-4o, etc.)
- OpenRouter
- Together AI
- Local Qwen Fallback (Offline GGUF / Llama-cpp & Smart Synthesis)
- Pre-flight validation, health checks, structured logging, & complete diagnostics.
"""

import os
import time
import uuid
import logging
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple, Generator

from app.agents.observability import traceable

from app.agents.llm_providers import (
    BaseLLMProvider,
    LLMProviderResponse,
    LLMRouterException,
    LLMAuthenticationError,
    LLMForbiddenError,
    LLMQuotaOrRateLimitError,
    LLMInvalidModelError,
    LLMTimeoutError,
    LLMConnectionError,
    LLMServerError,
    GroqProvider,
    normalize_groq_model,
    MetaLlamaProvider,
    OpenAIProvider,
    OpenRouterProvider,
    TogetherAIProvider,
    LocalQwenProvider,
)

logger = logging.getLogger(__name__)

# Standard model aliases mapping
MODEL_MAPPING = {
    "llama3-70b-8192": "llama-3.3-70b-versatile",
    "llama3-8b-8192": "llama-3.1-8b-instant",
    "mixtral-8x7b-32768": "llama-3.1-8b-instant",
    "gemma2-9b-it": "llama-3.1-8b-instant",
    "llama-3.3-70b-versatile": "llama-3.3-70b-versatile",
    "llama-3.3-70b": "llama-3.3-70b-versatile",
    "llama-3.3-70b-instruct": "llama-3.3-70b-versatile",
    "llama-3-70b-privacyguard": "llama-3.3-70b-versatile",
    "Llama-3.3-70B": "llama-3.3-70b-versatile",
    "Llama-3.1-8B": "llama-3.1-8b-instant",
    "llama-3.1-8b-instant": "llama-3.1-8b-instant",
    "llama-3.1-70b-versatile": "llama-3.3-70b-versatile",
}


@dataclass
class LLMResponse:
    """
    Standard response object maintaining 100% backward compatibility
    while exposing production MLOps return metadata.
    """
    content: str
    model_name: str
    engine_used: str
    finish_reason: str = "stop"
    raw_response: Optional[Any] = None
    error_note: Optional[str] = None
    provider_used: str = "Groq"
    routing_strategy: str = "Cloud"  # "Cloud", "Local", or "Fallback"
    fallback_reason: Optional[str] = None
    latency_ms: int = 0
    request_id: str = field(default_factory=lambda: f"req-{uuid.uuid4().hex[:12]}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "content": self.content,
            "model_used": self.model_name,
            "engine_used": self.engine_used,
            "provider_used": self.provider_used,
            "routing_strategy": self.routing_strategy,
            "fallback_reason": self.fallback_reason,
            "latency_ms": self.latency_ms,
            "request_id": self.request_id,
        }


class LLMRouter:
    """
    Centralized production LLM Router with deterministic failover and multi-provider dispatch.
    Providers supported:
    - Groq
    - Meta Llama API
    - OpenAI
    - OpenRouter
    - Together AI
    - Local Qwen
    """

    def __init__(self, default_model: str = "llama-3.3-70b-versatile"):
        self.default_model = MODEL_MAPPING.get(default_model, default_model)
        self.local_provider = LocalQwenProvider()

    def _resolve_provider_and_model(
        self,
        requested_model: Optional[str],
        override_groq_key: Optional[str] = None
    ) -> Tuple[BaseLLMProvider, str]:
        """
        Selects the appropriate LLM provider and normalized model name based on target model string and keys.
        """
        raw_model = requested_model or self.default_model
        norm_model = MODEL_MAPPING.get(raw_model, raw_model)
        lower_model = norm_model.lower()

        # Check explicit provider prefixes or model signatures
        if lower_model.startswith("openai/") or lower_model.startswith("gpt-"):
            key = os.getenv("OPENAI_API_KEY")
            return OpenAIProvider(api_key=key, default_model=norm_model.replace("openai/", "")), norm_model.replace("openai/", "")

        if lower_model.startswith("openrouter/") or lower_model.startswith("meta-llama/"):
            key = os.getenv("OPENROUTER_API_KEY")
            if key:
                return OpenRouterProvider(api_key=key, default_model=norm_model.replace("openrouter/", "")), norm_model.replace("openrouter/", "")

        if lower_model.startswith("together/"):
            key = os.getenv("TOGETHER_API_KEY")
            return TogetherAIProvider(api_key=key, default_model=norm_model.replace("together/", "")), norm_model.replace("together/", "")

        if lower_model.startswith("metallama/") or lower_model.startswith("llama-api/"):
            key = os.getenv("META_LLAMA_API_KEY")
            return MetaLlamaProvider(api_key=key, default_model=norm_model), norm_model

        # Default Primary Cloud Provider: Groq
        groq_key = override_groq_key if override_groq_key is not None else os.getenv("GROQ_API_KEY")
        target_groq_model = normalize_groq_model(norm_model)
        return GroqProvider(api_key=groq_key, default_model=target_groq_model), target_groq_model

    def _try_secondary_cloud_providers(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
        top_p: float
    ) -> Optional[Any]:
        """Attempts generation across secondary cloud providers if keys are configured."""
        candidates = [
            ("OpenRouter", os.getenv("OPENROUTER_API_KEY"), lambda k: OpenRouterProvider(api_key=k)),
            ("Together AI", os.getenv("TOGETHER_API_KEY"), lambda k: TogetherAIProvider(api_key=k)),
            ("OpenAI", os.getenv("OPENAI_API_KEY"), lambda k: OpenAIProvider(api_key=k)),
            ("Meta Llama", os.getenv("META_LLAMA_API_KEY"), lambda k: MetaLlamaProvider(api_key=k)),
        ]

        for name, key, builder in candidates:
            if key and len(key.strip()) > 0:
                try:
                    prov = builder(key.strip())
                    is_valid, _ = prov.validate_config()
                    if is_valid:
                        res = prov.generate(messages=messages, temperature=temperature, max_tokens=max_tokens, top_p=top_p)
                        if res and res.content:
                            return res
                except Exception as e:
                    logger.warning(f"[LLMRouter Auto-Failover] Secondary provider {name} failed: {e}")

        return None

    def health_check(self) -> Dict[str, Any]:
        """
        At application startup / runtime: verifies API key, endpoint, model availability.
        Returns status dict: Healthy, Warning, Error.
        """
        providers_status = {}
        overall_status = "Healthy"

        # Check Groq Provider
        groq_key = os.getenv("GROQ_API_KEY")
        groq = GroqProvider(api_key=groq_key)
        groq_check = groq.health_check()
        providers_status["Groq"] = groq_check
        if groq_check.get("status") == "Error":
            overall_status = "Warning" if groq_key else "Error"

        # Check Local Qwen
        local_check = self.local_provider.health_check()
        providers_status["Local Qwen"] = local_check

        # Check OpenAI if key present
        if os.getenv("OPENAI_API_KEY"):
            openai_p = OpenAIProvider()
            providers_status["OpenAI"] = openai_p.health_check()

        return {
            "status": overall_status,
            "active_cloud_provider": "Groq" if groq_key else "None",
            "providers": providers_status
        }

    @traceable(
        name="privacyshield.llm.route",
        run_type="llm",
        tags=["privacyshield", "llm-router", "pii-safe"],
    )
    def generate(
        self,
        messages: List[Dict[str, str]],
        model_name: Optional[str] = None,
        groq_api_key: Optional[str] = None,
        temperature: float = 0.15,
        max_tokens: int = 2048,
        top_p: float = 0.9,
        intent: str = "question",
        query: str = "",
        context: str = ""
    ) -> LLMResponse:
        """
        Executes deterministic multi-tier LLM generation:
        1. IF cloud provider configured:
             Validate API Key
             Validate Model Exists
             Run Pre-flight validation
             Call Cloud Model
             Success -> Return response
        2. ELSE / ON FAILURE:
             Log detailed reason (never swallow exceptions)
             Fallback to Local Qwen
             Return response with fallback metadata
        """
        req_id = f"req-{uuid.uuid4().hex[:12]}"
        start_time = time.time()

        debug_mode = os.getenv("DEBUG_LLM_ROUTING", "False").lower() in ("true", "1", "yes")

        provider, target_model = self._resolve_provider_and_model(model_name, override_groq_key=groq_api_key)

        api_key_present = bool(provider.api_key and len(provider.api_key.strip()) > 0)
        is_valid, validation_error = provider.validate_config(target_model)

        cloud_attempt = False
        cloud_success = False
        fallback_triggered = False
        fallback_reason = None
        last_exception_msg = None

        if debug_mode:
            prompt_str = str(messages)
            print("\n---------------------------------", flush=True)
            print(f"[DEBUG_LLM_ROUTING] Request ID: {req_id}", flush=True)
            print(f"[DEBUG_LLM_ROUTING] Selected Provider: {provider.provider_name}", flush=True)
            print(f"[DEBUG_LLM_ROUTING] Selected Model: {target_model}", flush=True)
            print(f"[DEBUG_LLM_ROUTING] API Key Present: {api_key_present}", flush=True)
            print(f"[DEBUG_LLM_ROUTING] Validation: {'PASS' if is_valid else f'FAIL ({validation_error})'}", flush=True)
            print(f"[DEBUG_LLM_ROUTING] Prompt Size: {len(prompt_str)} chars", flush=True)
            print(f"[DEBUG_LLM_ROUTING] Context Size: {len(context)} chars", flush=True)
            print("---------------------------------", flush=True)

        # -------------------------------------------------------------
        # Tier 1: Cloud Provider Call (Deterministic Execution)
        # -------------------------------------------------------------
        if is_valid:
            cloud_attempt = True
            try:
                prov_res = provider.generate(
                    messages=messages,
                    model_name=target_model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    top_p=top_p
                )
                cloud_success = True
                total_latency = int((time.time() - start_time) * 1000)

                # Structured log for successful cloud request
                logger.info(
                    f"\n---------------------------------\n"
                    f"Request ID: {req_id}\n"
                    f"Provider: {provider.provider_name}\n"
                    f"Model: {target_model}\n"
                    f"API Key: Present\n"
                    f"Validation: PASS\n"
                    f"Cloud Request: PASS\n"
                    f"Latency: {total_latency} ms\n"
                    f"Provider Used: {provider.provider_name}\n"
                    f"---------------------------------"
                )

                if debug_mode:
                    print(f"[DEBUG_LLM_ROUTING] Cloud Success: PASS ({total_latency} ms)", flush=True)

                return LLMResponse(
                    content=prov_res.content,
                    model_name=target_model,
                    engine_used=f"{provider.provider_name} Cloud API ({target_model})",
                    raw_response=prov_res.raw_response,
                    provider_used=provider.provider_name,
                    routing_strategy="Cloud",
                    fallback_reason=None,
                    latency_ms=total_latency,
                    request_id=req_id
                )

            except LLMAuthenticationError as e:
                fallback_reason = f"401 Unauthorized ({e.message})"
                last_exception_msg = str(e)
            except LLMForbiddenError as e:
                fallback_reason = f"403 Forbidden ({e.message})"
                last_exception_msg = str(e)
            except LLMQuotaOrRateLimitError as e:
                fallback_reason = f"429 Rate Limit Exceeded ({e.message})"
                last_exception_msg = str(e)
            except LLMInvalidModelError as e:
                fallback_reason = f"Invalid Model ({e.message})"
                last_exception_msg = str(e)
            except LLMTimeoutError as e:
                fallback_reason = f"Timeout ({e.message})"
                last_exception_msg = str(e)
            except LLMConnectionError as e:
                fallback_reason = f"Connection Failed ({e.message})"
                last_exception_msg = str(e)
            except LLMServerError as e:
                fallback_reason = f"Server Error {e.status_code} ({e.message})"
                last_exception_msg = str(e)
            except LLMRouterException as e:
                fallback_reason = f"Provider Error ({e.message})"
                last_exception_msg = str(e)
            except Exception as e:
                fallback_reason = f"Unexpected Error ({type(e).__name__}: {str(e)})"
                last_exception_msg = str(e)

        else:
            fallback_reason = validation_error or "Cloud provider validation failed."

        # -------------------------------------------------------------
        # Tier 2: Try Secondary Cloud Providers (Auto-Failover)
        # -------------------------------------------------------------
        sec_res = self._try_secondary_cloud_providers(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p
        )
        if sec_res:
            total_latency = int((time.time() - start_time) * 1000)
            logger.info(f"[LLMRouter Auto-Failover] Succeeded on secondary cloud provider '{sec_res.provider_name}' ({sec_res.model_name})")
            return LLMResponse(
                content=sec_res.content,
                model_name=sec_res.model_name,
                engine_used=f"{sec_res.provider_name} Cloud API ({sec_res.model_name})",
                raw_response=sec_res.raw_response,
                provider_used=sec_res.provider_name,
                routing_strategy="Cloud Auto-Failover",
                fallback_reason=None,
                latency_ms=total_latency,
                request_id=req_id
            )

        # -------------------------------------------------------------
        # Tier 3: Fallback to Local Qwen Engine
        # -------------------------------------------------------------
        fallback_triggered = True

        logger.warning(
            f"\n---------------------------------\n"
            f"Request ID: {req_id}\n"
            f"Provider: {provider.provider_name}\n"
            f"Validation: {'PASS' if is_valid else 'FAIL'}\n"
            f"Cloud Request: {'FAIL' if cloud_attempt else 'SKIPPED'}\n"
            f"Reason: {fallback_reason}\n"
            f"Fallback: Local Qwen\n"
            f"---------------------------------"
        )

        if debug_mode:
            print(f"[DEBUG_LLM_ROUTING] Fallback Triggered! Reason: {fallback_reason}", flush=True)

        local_res = self.local_provider.generate(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            intent=intent,
            query=query,
            context=context,
            fallback_reason=fallback_reason
        )

        total_latency = int((time.time() - start_time) * 1000)

        engine_name = "Local Qwen Engine"
        if fallback_reason:
            engine_name += f" (Fallback: {fallback_reason})"

        return LLMResponse(
            content=local_res.content,
            model_name=local_res.model_name,
            engine_used=engine_name,
            error_note=fallback_reason,
            provider_used="Local Qwen",
            routing_strategy="Fallback",
            fallback_reason=fallback_reason,
            latency_ms=total_latency,
            request_id=req_id
        )

    def generate_stream(
        self,
        messages: List[Dict[str, str]],
        model_name: Optional[str] = None,
        groq_api_key: Optional[str] = None,
        temperature: float = 0.15,
        max_tokens: int = 1024,
        top_p: float = 0.9
    ) -> Tuple[Any, str]:
        """Returns streaming completion stream from active cloud provider."""
        provider, target_model = self._resolve_provider_and_model(model_name, override_groq_key=groq_api_key)

        is_valid, err_reason = provider.validate_config(target_model)
        if not is_valid:
            raise LLMAuthenticationError(f"Streaming provider validation failed: {err_reason}", provider=provider.provider_name)

        return provider.generate_stream(
            messages=messages,
            model_name=target_model,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p
        )
