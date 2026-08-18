"""
PrivacyShield AI - DPDP Compliance & Guardrails Package.

Hybrid regulatory compliance engine:
- Deterministic statutory rule enforcement
- DPDP Act 2023 & Rules 2025 regulatory retrieval
- Local Qwen model legal explanation
- Structured audit-ready decisions
"""

from .dpdp_schemas import DPDPClause, ComplianceEvent, GuardrailDecision
from .dpdp_rule_engine import DPDPRuleEngine, RuleEvaluationResult
from .dpdp_retriever import DPDPRegulationsRetriever
from .dpdp_explainer_qwen import DPDPQwenExplainer
from .dpdp_guardrails_engine import (
    HybridDPDPGuardrailsEngine,
    DPDPViolationError,
    get_dpdp_guardrails_engine,
)

__all__ = [
    "DPDPClause",
    "ComplianceEvent",
    "GuardrailDecision",
    "DPDPRuleEngine",
    "RuleEvaluationResult",
    "DPDPRegulationsRetriever",
    "DPDPQwenExplainer",
    "HybridDPDPGuardrailsEngine",
    "DPDPViolationError",
    "get_dpdp_guardrails_engine",
]
