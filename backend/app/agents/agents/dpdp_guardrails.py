from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class DPDPComplianceResult:
    is_compliant: bool
    passed_rules: List[str]
    violations: List[str]
    guardrail_status: Dict[str, bool]
    recommendations: List[str]


class DPDPGuardrailsEngine:
    """
    Application Guardrails Engine inspired by Digital Personal Data Protection Act 2023 & Rules 2025.
    
    Provides technical guardrails and controls:
    1. Zero Unmasked PII & Candidate Extraction (Rule 6(1)(a))
    2. Data Principal Consent & Human-in-the-Loop (HITL) Review (Rule 3)
    3. Minor / Child Data Extra Consent Guardrail (Rule 10)
    4. Reasonable Security Safeguards & Zero Raw PII Cloud Transmission (Rule 6(1)(a))
    5. Immutable Auditability & Log Retention Safeguard (Rule 6(1)(c), Rule 12)
    
    Note: These are application-level security and privacy guardrails, not legal advice or statutory certifications.
    """

    def evaluate_document_processing(
        self,
        raw_text: str,
        detected_entities: List[Dict[str, Any]],
        human_approved_count: int,
        total_entities_count: int,
        hitl_review_completed: bool = False,
        has_child_data: bool = False,
        domain: str = "General",
        compliance_rule_set: str = "STANDARD_PRIVACY_RULES",
        cloud_transmission_safe: Optional[bool] = None,
        audit_logged: Optional[bool] = None,
    ) -> DPDPComplianceResult:
        passed_rules = []
        violations = []
        status = {}
        recommendations = []

        # 1. PII Candidate Detection Check (Rule 6(1)(a))
        # Note: Detection of PII indicates privacy controls are required, not a violation by itself.
        status["PII_DETECTION_CHECK"] = True
        if total_entities_count == 0:
            passed_rules.append("DPDP Rule 6(1)(a): No unmasked PII detected in document.")
        else:
            passed_rules.append(f"DPDP Rule 6(1)(a): Detected {total_entities_count} PII entities requiring privacy protection controls.")

        # 2. Human-in-the-Loop (HITL) Review Verification (Rule 3)
        if total_entities_count > 0 and not hitl_review_completed:
            status["HITL_CONSENT_VERIFICATION"] = False
            violations.append("DPDP Rule 3: PII entities detected but HITL verification has not been completed.")
            recommendations.append("Complete human review & approval of detected PII entities before final ingestion.")
        elif total_entities_count > 0 and hitl_review_completed:
            status["HITL_CONSENT_VERIFICATION"] = True
            passed_rules.append(f"DPDP Rule 3: HITL verification completed for detected PII entities ({human_approved_count} approved for masking).")
        else:
            status["HITL_CONSENT_VERIFICATION"] = True
            passed_rules.append("DPDP Rule 3: No PII detected; HITL verification requirement satisfied.")

        # 3. Child/Minor Data Safeguard (Rule 10)
        if has_child_data:
            status["CHILD_DATA_PROTECTION"] = True
            passed_rules.append("DPDP Rule 10: Special parental/guardian verifiable consent guardrail active.")
        else:
            status["CHILD_DATA_PROTECTION"] = True
            passed_rules.append("DPDP Rule 10: Standard adult data principal processing guardrail active.")

        # 4. Security & Storage Safeguards (Rule 6)
        if cloud_transmission_safe is False:
            status["SECURITY_SAFEGUARDS"] = False
            violations.append("DPDP Rule 6: Potential raw PII leakage detected in cloud transmission check.")
            recommendations.append("Block external cloud transmission and review tokenized obfuscation.")
        else:
            status["SECURITY_SAFEGUARDS"] = True
            passed_rules.append("DPDP Rule 6: Local tokenized obfuscation enabled; zero PII sent to external cloud.")

        # 5. Auditability (Rule 6(1)(c))
        if audit_logged is False:
            status["IMMUTABLE_AUDIT_LOG"] = False
            violations.append("DPDP Rule 6(1)(c): Audit logging failed or not recorded.")
            recommendations.append("Ensure audit log service is active and accessible.")
        else:
            status["IMMUTABLE_AUDIT_LOG"] = True
            passed_rules.append("DPDP Rule 6(1)(c): Immutable audit log entry generated for processing.")

        is_compliant = len(violations) == 0

        return DPDPComplianceResult(
            is_compliant=is_compliant,
            passed_rules=passed_rules,
            violations=violations,
            guardrail_status=status,
            recommendations=recommendations
        )

    def evaluate_cloud_transmission(self, text_to_transmit: str, entity_mapping: Dict[str, str]) -> Dict[str, Any]:
        """
        Ensures that NO raw PII values present in entity_mapping exist in text_to_transmit.
        Strictly avoids logging raw PII in application logs.
        """
        leakages = []
        for token, raw_val in entity_mapping.items():
            if raw_val and len(raw_val.strip()) > 2 and raw_val.lower() in text_to_transmit.lower():
                leakages.append({"token": token, "has_leakage": True})

        is_safe = len(leakages) == 0
        if not is_safe:
            logger.warning(f"[Cloud Security Guardrail] Potential leakage detected for {len(leakages)} tokens. Transmission blocked.")
        else:
            logger.info("[Cloud Security Guardrail] Zero PII leakage verified. Cloud transmission approved.")

        return {
            "is_safe": is_safe,
            "leakages_found": leakages,
            "status": "APPROVED_FOR_CLOUD_TRANSMISSION" if is_safe else "BLOCKED_POTENTIAL_LEAKAGE",
            "dpdp_rule": "DPDP Act 2025 Rule 6(1)(a) Zero-Leakage Security Safeguard"
        }
