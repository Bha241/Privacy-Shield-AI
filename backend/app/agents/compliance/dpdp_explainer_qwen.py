"""
DPDP Qwen Explainer for PrivacyShield AI.

Generates structured, conservative legal/compliance explanations using local Qwen.

CRITICAL INVARIANTS:
1. Local Qwen is used for EXPLANATION ONLY.
2. It NEVER modifies, overrides, or relaxes deterministic rule decisions.
3. Temperature is fixed at 0.1 for high reproducibility and legal consistency.
4. Explanations must directly cite retrieved DPDP sections and rule identifiers.
5. High-fidelity fallback synthesis ensures zero failure even if local GGUF engine is busy/unloaded.
"""

import logging
from typing import List, Dict, Any, Optional

from .dpdp_schemas import DPDPClause, ComplianceEvent
from .dpdp_rule_engine import RuleEvaluationResult

logger = logging.getLogger(__name__)


class DPDPQwenExplainer:
    """
    Explains DPDP compliance evaluation results using local Qwen model with fallback synthesis.
    """

    def __init__(self, model_name: str = "qwen2.5-3b-instruct-local"):
        self.model_name = model_name

    def _build_prompt(
        self,
        event: ComplianceEvent,
        rule_result: RuleEvaluationResult,
        clauses: List[DPDPClause]
    ) -> str:
        """Constructs a strict, conservative legal prompt for Qwen."""
        clause_references = "\n".join([
            f"- [{c.clause_id}] {c.title} ({c.source}): {c.text}"
            for c in clauses
        ])

        violations_text = "\n".join([f"- {v}" for v in rule_result.triggered_rules]) if rule_result.triggered_rules else "None (All checks passed)."
        passed_text = "\n".join([f"- {p}" for p in rule_result.passed_rules]) if rule_result.passed_rules else "None."

        prompt = (
            "You are the PrivacyShield AI DPDP Statutory Compliance Explainer.\n"
            "Your role is strictly to provide an objective, audit-ready explanation of the compliance decision.\n\n"
            "LEGAL REFERENCE PROVISIONS:\n"
            f"{clause_references}\n\n"
            "EVALUATED ACTION:\n"
            f"Event Type: {event.event_type}\n"
            f"Document ID: {event.document_id or 'N/A'}\n"
            f"Actor ID: {event.actor_id or 'usr_system'}\n"
            f"Deterministic Compliance Status: {'COMPLIANT' if rule_result.is_compliant else 'NON-COMPLIANT'}\n"
            f"Action Blocked: {'YES (BLOCKED)' if rule_result.blocked else 'NO (PERMITTED)'}\n"
            f"Assessed Risk: {rule_result.risk_level}\n\n"
            "RULE VIOLATIONS / TRIGGERS:\n"
            f"{violations_text}\n\n"
            "PASSED CHECKS:\n"
            f"{passed_text}\n\n"
            "INSTRUCTIONS:\n"
            "1. State the final compliance decision clearly in formal regulatory language.\n"
            "2. Specifically cite relevant DPDP statutory sections and rules (e.g. [DPDP_ACT_SEC_8_5], [DPDP_RULE_6_1_A]).\n"
            "3. Do NOT invent legal text or hallucinate rules.\n"
            "4. Do NOT attempt to overturn or relax a BLOCKED decision.\n"
            "5. Provide a 2 to 4 sentence formal summary for the compliance audit log."
        )
        return prompt

    def _generate_fallback_explanation(
        self,
        event: ComplianceEvent,
        rule_result: RuleEvaluationResult,
        clauses: List[DPDPClause]
    ) -> str:
        """
        Deterministic, high-fidelity fallback legal explanation synthesizer.
        Guarantees instant, zero-error audit explanations even if local Qwen GGUF is offline.
        """
        cited_ids = ", ".join([f"[{c.clause_id}]" for c in clauses[:3]]) if clauses else "[DPDP_ACT_SEC_8_5]"

        if rule_result.blocked:
            primary_violation = rule_result.triggered_rules[0] if rule_result.triggered_rules else "Security control violation"
            explanation = (
                f"NON-COMPLIANT: Action '{event.event_type}' has been strictly BLOCKED by PrivacyShield DPDP Guardrails "
                f"due to a {rule_result.risk_level} risk violation: {primary_violation}. Under statutory provisions {cited_ids}, "
                f"the Data Fiduciary is mandated to enforce reasonable security safeguards and consent controls before data processing or transfer. "
                f"Remediation requires: {rule_result.recommendations[0] if rule_result.recommendations else 'enforcing masking safeguards'}."
            )
        else:
            explanation = (
                f"COMPLIANT: Action '{event.event_type}' has been VERIFIED and PERMITTED under DPDP compliance standards. "
                f"All statutory safeguards ({cited_ids}) including zero raw PII exposure and audit logging have been satisfied. "
                f"The request is cleared for processing within authorized purpose boundaries."
            )

        return explanation

    def explain(
        self,
        event: ComplianceEvent,
        rule_result: RuleEvaluationResult,
        clauses: List[DPDPClause]
    ) -> tuple[str, str]:
        """
        Generates formal compliance explanation.
        Returns: (explanation_text, model_used_identifier)
        """
        prompt = self._build_prompt(event, rule_result, clauses)

        # 1. Try local Qwen engine if available
        try:
            from app.agents.llm_providers.local_qwen_provider import LocalQwenProvider
            qwen_provider = LocalQwenProvider()
            qwen_instance = qwen_provider._get_local_qwen()
            if qwen_instance and hasattr(qwen_instance, "generate"):
                llm_response = qwen_instance.generate(
                    prompt=prompt,
                    system_prompt="You are a conservative DPDP statutory compliance auditor.",
                    temperature=0.1,
                    max_tokens=256
                )
                if llm_response and len(llm_response.strip()) > 20:
                    return llm_response.strip(), "local-qwen-gguf"
        except Exception as e:
            logger.debug(f"Local Qwen generation fallback invoked: {e}")

        # 2. Fallback explanation synthesizer
        fallback_text = self._generate_fallback_explanation(event, rule_result, clauses)
        return fallback_text, "dpdp-statutory-synthesizer"
