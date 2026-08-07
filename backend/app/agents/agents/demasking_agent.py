from typing import Dict, Any, Optional
from pii_detector.masking.pii_masker import PIIMasker


class DemaskingAgent:
    """
    4. De-masking Agent:
    Responsible for dynamically restoring original PII values from masked tokens
    when requested by the user or when Human-in-the-Loop approval is granted in the Chat.
    """

    def __init__(self):
        self.masker = PIIMasker()

    def demask_text(self, masked_text: str, mapping: Dict[str, str], user_approved: bool = True) -> Dict[str, Any]:
        """
        De-masks masked_text using mapping if user approval is granted.
        """
        if not user_approved:
            return {
                "status": "blocked",
                "reason": "Human approval required for de-masking.",
                "output_text": masked_text,
                "is_demasked": False
            }

        unmasked_text = self.masker.unmask(masked_text, mapping)
        tokens_replaced = [tok for tok in mapping.keys() if tok in masked_text]

        return {
            "status": "success",
            "output_text": unmasked_text,
            "tokens_replaced": tokens_replaced,
            "replaced_count": len(tokens_replaced),
            "is_demasked": True
        }
