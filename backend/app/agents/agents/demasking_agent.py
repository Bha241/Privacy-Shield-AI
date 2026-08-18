import logging
from typing import Dict, Any, Optional, List
from pii_detector.masking.pii_masker import PIIMasker

logger = logging.getLogger(__name__)


class DemaskingAgent:
    """
    4. De-masking Agent:
    Responsible for dynamically restoring original PII values from masked tokens
    ONLY when explicit, authorized Human-in-the-Loop approval is granted.
    
    Security Guarantee:
    - High-sensitivity operation: Fails closed by default.
    - Explicit approval required: `user_approved` defaults to False.
    - Zero raw PII logging: Tokens and metadata logged without exposing sensitive original values.
    """

    def __init__(self):
        self.masker = PIIMasker()

    def demask_text(
        self,
        masked_text: str,
        mapping: Dict[str, str],
        user_approved: bool = False,
        audit_agent: Optional[Any] = None,
        document_id: Optional[str] = None,
        actor_id: str = "usr_system"
    ) -> Dict[str, Any]:
        """
        De-masks masked_text using mapping ONLY if explicit user approval is granted.
        Fails closed by default.
        """
        # 1. Fail closed if not explicitly authorized
        if user_approved is not True:
            logger.warning("[DemaskingAgent] De-masking blocked: explicit human approval is required.")
            if audit_agent:
                try:
                    audit_agent.log_event(
                        agent_name="DemaskingAgent",
                        action_type="DEMASK_REQUEST",
                        actor_id=actor_id,
                        document_id=document_id,
                        user_approved=False,
                        dpdp_compliant=True,
                        details={
                            "action": "DEMASK_REQUEST",
                            "status": "blocked",
                            "reason": "Explicit human approval is required for de-masking.",
                            "tokens_requested_count": len(mapping) if mapping else 0,
                            "tokens_replaced_count": 0,
                            "authorization": "blocked_unauthorized"
                        }
                    )
                except Exception as e:
                    logger.warning(f"[DemaskingAgent] Audit log notice: {type(e).__name__}")

            return {
                "status": "blocked",
                "reason": "Explicit human approval is required for de-masking.",
                "output_text": masked_text,
                "tokens_replaced": [],
                "replaced_count": 0,
                "is_demasked": False
            }

        # 2. Handle empty masked text
        if not masked_text:
            return {
                "status": "success",
                "output_text": masked_text or "",
                "tokens_replaced": [],
                "replaced_count": 0,
                "is_demasked": False
            }

        # 3. Handle empty mapping
        if not mapping:
            return {
                "status": "success",
                "output_text": masked_text,
                "tokens_replaced": [],
                "replaced_count": 0,
                "is_demasked": False
            }

        try:
            # 4. Safely filter replaced tokens to only those present in masked_text
            tokens_replaced: List[str] = [
                token for token in mapping.keys()
                if isinstance(token, str) and token in masked_text
            ]

            # 5. Restore original text using underlying masker
            unmasked_text = self.masker.unmask(masked_text, mapping)

            logger.info(f"[DemaskingAgent] Successfully de-masked {len(tokens_replaced)} tokens.")

            # 6. Audit successful demasking without exposing raw PII or mapping values
            if audit_agent:
                try:
                    audit_agent.log_event(
                        agent_name="DemaskingAgent",
                        action_type="DEMASK_REQUEST",
                        actor_id=actor_id,
                        document_id=document_id,
                        user_approved=True,
                        dpdp_compliant=True,
                        details={
                            "action": "DEMASK_REQUEST",
                            "status": "success",
                            "tokens_requested_count": len(mapping),
                            "tokens_replaced_count": len(tokens_replaced),
                            "authorization": "approved"
                        }
                    )
                except Exception as e:
                    logger.warning(f"[DemaskingAgent] Audit log notice: {type(e).__name__}")

            return {
                "status": "success",
                "output_text": unmasked_text,
                "tokens_replaced": tokens_replaced,
                "replaced_count": len(tokens_replaced),
                "is_demasked": True
            }

        except Exception as e:
            logger.error(f"[DemaskingAgent] Error during de-masking operation: {type(e).__name__}")
            if audit_agent:
                try:
                    audit_agent.log_event(
                        agent_name="DemaskingAgent",
                        action_type="DEMASK_REQUEST",
                        actor_id=actor_id,
                        document_id=document_id,
                        user_approved=True,
                        dpdp_compliant=False,
                        details={
                            "action": "DEMASK_REQUEST",
                            "status": "error",
                            "tokens_requested_count": len(mapping) if mapping else 0,
                            "tokens_replaced_count": 0,
                            "error": type(e).__name__
                        }
                    )
                except Exception as audit_err:
                    logger.warning(f"[DemaskingAgent] Audit log notice: {type(audit_err).__name__}")

            return {
                "status": "error",
                "reason": "An error occurred during de-masking.",
                "output_text": masked_text,
                "tokens_replaced": [],
                "replaced_count": 0,
                "is_demasked": False
            }
