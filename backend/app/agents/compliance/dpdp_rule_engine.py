"""
Deterministic DPDP Rule Engine for PrivacyShield AI.

Enforces non-negotiable statutory security and compliance rules in Python code:
1. Zero Raw PII to Cloud (Section 8(5), Rule 6(1)(a))
2. Human-In-The-Loop (HITL) Verification (Rule 3, Section 6)
3. Minor / Child Data Consent Guardrail (Section 9, Rule 10)
4. Mandatory Immutable Audit Logging (Section 8(4), Rule 12)
5. Purpose Specification for Demasking (Section 6, Rule 4)

CRITICAL PRINCIPLE: Hard security rules are deterministic. LLMs are NEVER allowed
to override or relax these blocking decisions.
"""

from typing import Dict, Any, List, Tuple
from dataclasses import dataclass

from .dpdp_schemas import ComplianceEvent


@dataclass
class RuleEvaluationResult:
    """Output of deterministic rule evaluation."""
    is_compliant: bool
    blocked: bool
    risk_level: str  # LOW, MEDIUM, HIGH, CRITICAL
    triggered_rules: List[str]
    passed_rules: List[str]
    recommendations: List[str]


class DPDPRuleEngine:
    """
    Deterministic rule engine that validates compliance events against DPDP statutory requirements.
    """

    def evaluate(self, event: ComplianceEvent | Dict[str, Any]) -> RuleEvaluationResult:
        """
        Runs all deterministic DPDP compliance checks against the event payload.
        """
        if isinstance(event, dict):
            event = ComplianceEvent(**event)

        triggered_rules: List[str] = []
        passed_rules: List[str] = []
        recommendations: List[str] = []

        is_blocked = False
        highest_risk = "LOW"

        def escalate_risk(level: str):
            nonlocal highest_risk
            risk_ranks = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
            if risk_ranks.get(level, 1) > risk_ranks.get(highest_risk, 1):
                highest_risk = level

        # ----------------------------------------------------------------------
        # Rule 1: Zero Raw PII Transmission to Cloud (Sec 8(5) & Rule 6(1)(a))
        # ----------------------------------------------------------------------
        if event.raw_pii_to_cloud or (event.event_type == "CLOUD_TRANSMISSION" and event.raw_pii_to_cloud):
            triggered_rules.append(
                "RULE_ZERO_RAW_PII_CLOUD: Raw/unmasked PII transmission to external cloud services is strictly forbidden."
            )
            recommendations.append(
                "Ensure reversible tokenization is applied before routing payloads to external LLMs."
            )
            is_blocked = True
            escalate_risk("CRITICAL")
        else:
            passed_rules.append(
                "RULE_ZERO_RAW_PII_CLOUD: Zero raw PII payload verified for cloud transfer."
            )

        # ----------------------------------------------------------------------
        # Rule 2: HITL Consent & Review Verification (Rule 3 & Section 6)
        # ----------------------------------------------------------------------
        if event.hitl_required and not event.hitl_approved:
            triggered_rules.append(
                "RULE_HITL_VERIFICATION: High-risk or sensitive entity extraction requires completed Human-in-the-Loop approval."
            )
            recommendations.append(
                "Submit document for Data Protection Officer (DPO) or admin HITL review before downstream processing."
            )
            is_blocked = True
            escalate_risk("HIGH")
        elif event.hitl_required and event.hitl_approved:
            passed_rules.append(
                "RULE_HITL_VERIFICATION: HITL review verified and approved."
            )

        # ----------------------------------------------------------------------
        # Rule 3: Child / Minor Data Safeguards (Section 9 & Rule 10)
        # ----------------------------------------------------------------------
        if event.has_child_data and not event.child_consent_verified:
            triggered_rules.append(
                "RULE_CHILD_DATA_PROTECTION: Processing personal data of minors (<18 years) requires verifiable parental consent."
            )
            recommendations.append(
                "Collect and cryptographically verify parental/guardian consent prior to processing minor records."
            )
            is_blocked = True
            escalate_risk("CRITICAL")
        elif event.has_child_data and event.child_consent_verified:
            passed_rules.append(
                "RULE_CHILD_DATA_PROTECTION: Minor data with verified parental consent approved."
            )

        # ----------------------------------------------------------------------
        # Rule 4: Mandatory Immutable Audit Logging (Section 8(4) & Rule 12)
        # ----------------------------------------------------------------------
        if not event.audit_written:
            triggered_rules.append(
                "RULE_AUDIT_LOG_MANDATORY: Processing action must be immutably recorded in the security audit ledger."
            )
            recommendations.append(
                "Ensure audit_log_agent writes cryptographic transaction entry to privacyshield.db before executing action."
            )
            is_blocked = True
            escalate_risk("HIGH")
        else:
            passed_rules.append(
                "RULE_AUDIT_LOG_MANDATORY: Audit logging verified."
            )

        # ----------------------------------------------------------------------
        # Rule 5: Purpose Specification on Demasking (Section 6 & Rule 4)
        # ----------------------------------------------------------------------
        if event.event_type == "DEMASKING" and not event.purpose:
            triggered_rules.append(
                "RULE_PURPOSE_LIMITATION: Demasking sensitive tokens requires an explicit, audited business purpose."
            )
            recommendations.append(
                "Provide a valid 'purpose' string in the demasking request payload."
            )
            is_blocked = True
            escalate_risk("HIGH")
        elif event.event_type == "DEMASKING" and event.purpose:
            passed_rules.append(
                f"RULE_PURPOSE_LIMITATION: Purpose '{event.purpose}' validated for token demasking."
            )

        # Overall compliance determination
        is_compliant = (len(triggered_rules) == 0) and (not is_blocked)

        if is_compliant and highest_risk == "LOW":
            recommendations.append("Continue standard privacy-preserving pipeline operations.")

        return RuleEvaluationResult(
            is_compliant=is_compliant,
            blocked=is_blocked,
            risk_level=highest_risk,
            triggered_rules=triggered_rules,
            passed_rules=passed_rules,
            recommendations=recommendations
        )
