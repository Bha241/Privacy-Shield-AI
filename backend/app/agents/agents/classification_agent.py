from typing import Dict, Any
import re


class ClassificationAgent:
    """
    1. Classification Agent (SRS FR-1.1 - 1.4):
    Classifies documents into Financial, Medical, HR, Legal, or General categories,
    computes confidence scores, and associates applicable compliance rule sets.
    """

    CATEGORIES = {
        "Financial": ["bank", "pan", "account", "invoice", "statement", "tax", "salary", "credit", "debit", "balance", "amount", "rs.", "inr", "salary"],
        "Medical": ["patient", "diagnosis", "doctor", "hospital", "prescription", "treatment", "health", "medical", "blood", "report", "clinic"],
        "HR": ["employee", "resume", "designation", "joining", "performance", "department", "appraisal", "salary", "pf", "experience"],
        "Legal": ["agreement", "contract", "clause", "party", "court", "jurisdiction", "affidavit", "witness", "legal", "terms"],
    }

    def classify_document(self, text: str) -> Dict[str, Any]:
        text_lower = text.lower()

        scores = {}
        for cat, keywords in self.CATEGORIES.items():
            count = sum(len(re.findall(r'\b' + re.escape(kw) + r'\b', text_lower)) for kw in keywords)
            scores[cat] = count

        max_cat = max(scores, key=scores.get)
        max_score = scores[max_cat]

        if max_score == 0:
            category = "General"
            confidence = 0.85
        else:
            total_hits = sum(scores.values())
            category = max_cat
            confidence = min(0.98, round(max_score / max(1, total_hits) + 0.5, 2))

        # Assign compliance rule set as per FR-1.2
        rule_set = "DPDP_ACT_2025_RULES" if category in ["Medical", "Financial", "HR"] else "STANDARD_PRIVACY_RULES"

        return {
            "category": category,
            "confidence_score": confidence,
            "compliance_rule_set": rule_set,
            "requires_manual_override": confidence < 0.70
        }
