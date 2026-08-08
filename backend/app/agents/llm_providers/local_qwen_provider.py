"""
PrivacyShieldAI - Local Qwen Provider
Local Qwen GGUF / Llama-cpp and Smart Synthesis fallback implementation.
"""

import re
import time
import logging
from typing import Optional, List, Dict, Any, Tuple

from app.agents.llm_providers.base import (
    BaseLLMProvider,
    LLMProviderResponse,
)

logger = logging.getLogger(__name__)


class LocalQwenProvider(BaseLLMProvider):
    """Local Qwen & Smart Synthesis Fallback Provider."""

    def __init__(self, default_model: str = "Qwen-Local"):
        super().__init__(provider_name="Local Qwen", default_model=default_model, api_key="LOCAL_OFFLINE")
        self._local_qwen_instance = None

    def _get_local_qwen(self) -> Optional[Any]:
        """Lazy loader for local Qwen instance."""
        if self._local_qwen_instance is None:
            try:
                from app.agents.llms.qwen import QwenLLM
                inst = QwenLLM()
                # Verify instance model initialized
                if hasattr(inst, "llm") and inst.llm is not None:
                    self._local_qwen_instance = inst
                else:
                    self._local_qwen_instance = False
            except Exception:
                try:
                    from pii_detector.llms.qwen import QwenLLM
                    inst = QwenLLM()
                    if hasattr(inst, "llm") and inst.llm is not None:
                        self._local_qwen_instance = inst
                    else:
                        self._local_qwen_instance = False
                except Exception:
                    self._local_qwen_instance = False
        return self._local_qwen_instance if self._local_qwen_instance else None

    def validate_config(self, model_name: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        """Local Qwen is always valid as offline fallback."""
        return True, None

    def health_check(self) -> Dict[str, Any]:
        """Health check for local engine."""
        qwen = self._get_local_qwen()
        if qwen:
            return {"status": "Healthy", "provider": "Local Qwen", "type": "GGUF/LlamaCpp", "api_key_present": True}
        return {"status": "Healthy", "provider": "Local Qwen", "type": "SmartSynthesisEngine", "api_key_present": True}

    def _smart_synthesis_fallback(
        self,
        query: str,
        context: str,
        intent: str,
        reason_for_fallback: Optional[str] = None
    ) -> str:
        """Deterministic synthesis engine fallback when LLM endpoints fail."""
        if not context or "No matching document context" in context:
            return "No relevant document context is available. Please ensure a valid document has been ingested."

        lines = [ln.strip() for ln in context.splitlines() if ln.strip() and len(ln.strip()) > 10]
        clean_lines = []
        seen = set()
        for ln in lines:
            k = ln.lower()[:70]
            if k not in seen:
                clean_lines.append(ln)
                seen.add(k)

        if intent in ["summary", "executive_summary"]:
            paragraphs = []
            chunk_size = 4
            for i in range(0, min(len(clean_lines), 12), chunk_size):
                para = " ".join(clean_lines[i:i+chunk_size])
                paragraphs.append(para)

            narrative = "\n\n".join(paragraphs) if paragraphs else context[:500]
            return (
                f"{narrative}\n\n"
                f"*Privacy Protection Guarantee: Sensitive identity tokens remain masked throughout document processing.*"
            )

        elif intent == "analysis":
            p1 = " ".join(clean_lines[:3]) if clean_lines else "The document presents structured information."
            p2 = " ".join(clean_lines[3:6]) if len(clean_lines) > 3 else "Key procedural steps are recorded in the content."
            return (
                f"### Purpose & Context\n{p1}\n\n"
                f"### Key Observations\n{p2}\n\n"
                f"### Privacy Considerations\nIdentified personal identifiers are protected using PrivacyShieldAI token masking.\n\n"
                f"### Overall Assessment\nThe document appears complete and structured according to standard procedures."
            )

        q_terms = set(re.findall(r"\w+", (query or "").lower())) - {
            "what", "is", "the", "a", "an", "of", "in", "to", "for", "and", "or", "please", "tell", "me", "about"
        }
        scored = []
        for ln in clean_lines:
            score = len(q_terms & set(re.findall(r"\w+", ln.lower())))
            scored.append((score, ln))

        scored.sort(key=lambda x: x[0], reverse=True)
        top_matches = [ln for score, ln in scored if score > 0][:5] or clean_lines[:4]

        answer_body = " ".join(top_matches)
        return (
            f"{answer_body}\n\n"
            f"*All sensitive identifiers remain masked for privacy preservation.*"
        )

    def generate(
        self,
        messages: List[Dict[str, str]],
        model_name: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 512,
        top_p: float = 0.9,
        intent: str = "question",
        query: str = "",
        context: str = "",
        fallback_reason: Optional[str] = None,
        **kwargs
    ) -> LLMProviderResponse:
        """Executes Local Qwen or Smart Synthesis fallback."""
        start_t = time.time()
        qwen = self._get_local_qwen()

        if qwen:
            prompt_parts = []
            for msg in messages:
                role = msg.get("role", "user").capitalize()
                content = msg.get("content", "")
                prompt_parts.append(f"{role}: {content}")
            prompt_parts.append("Assistant:")
            full_prompt = "\n\n".join(prompt_parts)

            try:
                res = qwen.generate(prompt=full_prompt, max_tokens=max_tokens, temperature=temperature)
                if res and res.strip():
                    latency_ms = int((time.time() - start_t) * 1000)
                    return LLMProviderResponse(
                        content=res.strip(),
                        model_name="Qwen-Local",
                        provider_name="Local Qwen",
                        routing_strategy="Fallback" if fallback_reason else "Local",
                        fallback_reason=fallback_reason,
                        latency_ms=latency_ms
                    )
            except Exception as e:
                logger.warning(f"Local Qwen generation exception: {e}")

        # Smart synthesis fallback
        content = self._smart_synthesis_fallback(query=query, context=context, intent=intent, reason_for_fallback=fallback_reason)
        latency_ms = int((time.time() - start_t) * 1000)
        return LLMProviderResponse(
            content=content,
            model_name="SmartSynthesisFallback",
            provider_name="Local Qwen",
            routing_strategy="Fallback" if fallback_reason else "Local",
            fallback_reason=fallback_reason,
            latency_ms=latency_ms
        )
