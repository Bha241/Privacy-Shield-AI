"""
Hybrid DPDP Compliance & Guardrails Engine for PrivacyShield AI.

Coordinates:
1. Deterministic statutory rule checks (Hard security gating)
2. Semantic & keyword vector retrieval over DPDP regulations corpus
3. Local Qwen model for audit-ready compliance explanation
4. Structured GuardrailDecision output with complete audit trails

CRITICAL INVARIANT:
Hard security rules in DPDPRuleEngine dictate the 'blocked' and 'is_compliant'
decision. The LLM acts strictly as an explainer and cannot override or relax rules.
"""

import time
import logging
from typing import Dict, Any, Optional

from .dpdp_schemas import DPDPClause, ComplianceEvent, GuardrailDecision
from .dpdp_rule_engine import DPDPRuleEngine, RuleEvaluationResult
from .dpdp_retriever import DPDPRegulationsRetriever
from .dpdp_explainer_qwen import DPDPQwenExplainer

logger = logging.getLogger(__name__)


class DPDPViolationError(Exception):
    """Raised when a non-compliant action is blocked by DPDP guardrails."""
    def __init__(self, message: str, decision: GuardrailDecision):
        super().__init__(message)
        self.decision = decision


class HybridDPDPGuardrailsEngine:
    """
    Enterprise hybrid compliance engine combining deterministic rule gating,
    vectorized regulatory knowledge, and local LLM explanation.
    """

    def __init__(
        self,
        rule_engine: Optional[DPDPRuleEngine] = None,
        retriever: Optional[DPDPRegulationsRetriever] = None,
        explainer: Optional[DPDPQwenExplainer] = None
    ):
        self.rule_engine = rule_engine or DPDPRuleEngine()
        self.retriever = retriever or DPDPRegulationsRetriever()
        self.explainer = explainer or DPDPQwenExplainer()

    def evaluate_event(self, event: ComplianceEvent | Dict[str, Any]) -> GuardrailDecision:
        """
        Main compliance evaluation pipeline.

        Args:
            event: ComplianceEvent or dictionary containing action parameters.

        Returns:
            GuardrailDecision containing compliance determination, blocked status,
            statutory clause citations, explanation, and remediation steps.
        """
        start_time = time.time()

        if isinstance(event, dict):
            event_obj = ComplianceEvent(**event)
        else:
            event_obj = event

        # 1. Deterministic Rule Evaluation (Hard Security Gate)
        rule_result: RuleEvaluationResult = self.rule_engine.evaluate(event_obj)

        # 2. Build Regulatory Retrieval Query
        query = self.retriever.map_event_to_query(
            event_type=event_obj.event_type,
            triggered_rules=rule_result.triggered_rules
        )

        # 3. Retrieve Relevant DPDP Statutory Clauses & Rules
        retrieved_clauses = self.retriever.retrieve(query=query, top_k=4)

        # 4. Generate Formal Legal Explanation with Local Qwen
        explanation_text, model_used = self.explainer.explain(
            event=event_obj,
            rule_result=rule_result,
            clauses=retrieved_clauses
        )

        elapsed_ms = round((time.time() - start_time) * 1000, 2)

        # 5. Build Final Immutable Guardrail Decision
        # Invariant check: If rule_result.blocked is True, decision MUST be blocked!
        decision = GuardrailDecision(
            event_type=event_obj.event_type,
            is_compliant=rule_result.is_compliant,
            blocked=rule_result.blocked,
            risk_level=rule_result.risk_level,
            triggered_rules=rule_result.triggered_rules,
            passed_rules=rule_result.passed_rules,
            retrieved_clauses=retrieved_clauses,
            explanation=explanation_text,
            recommendations=rule_result.recommendations,
            model_used=model_used,
            metadata={
                "document_id": event_obj.document_id,
                "actor_id": event_obj.actor_id,
                "evaluation_time_ms": elapsed_ms,
                "retrieved_clause_count": len(retrieved_clauses),
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            }
        )

        if decision.blocked:
            logger.warning(
                f"[DPDP GUARDRAIL BLOCKED] Event: {event_obj.event_type} | "
                f"Risk: {decision.risk_level} | Violations: {decision.triggered_rules}"
            )
        else:
            logger.info(
                f"[DPDP GUARDRAIL PASSED] Event: {event_obj.event_type} | Risk: {decision.risk_level}"
            )

        return decision

    def enforce_guardrail(self, event: ComplianceEvent | Dict[str, Any]) -> GuardrailDecision:
        """
        Evaluates the event and raises DPDPViolationError if the action is blocked.
        Useful for FastAPI middleware and pipeline security guards.
        """
        decision = self.evaluate_event(event)
        if decision.blocked:
            raise DPDPViolationError(
                message=f"DPDP Compliance Violation: {decision.explanation}",
                decision=decision
            )
        return decision


# Singleton instance helper
_engine_instance: Optional[HybridDPDPGuardrailsEngine] = None


def get_dpdp_guardrails_engine() -> HybridDPDPGuardrailsEngine:
    """Returns the shared singleton instance of HybridDPDPGuardrailsEngine."""
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = HybridDPDPGuardrailsEngine()
    return _engine_instance
