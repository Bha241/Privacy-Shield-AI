from typing import Dict, Any
import re


class ClassificationAgent:
    """
    Document Classification Agent.

    Responsibilities:
    1. Classify documents into:
       Financial, Medical, HR, Legal, Supply Chain, Commerce, General.
    2. Calculate a confidence score.
    3. Determine the applicable compliance rule set.
    4. Flag ambiguous classifications for HITL/manual review.

    This implementation is intentionally lightweight and deterministic.
    It can later be replaced or combined with an ML/LLM classifier.
    """

    # ------------------------------------------------------------------
    # Domain keywords
    # ------------------------------------------------------------------
    CATEGORIES: Dict[str, list[str]] = {
        "Financial": [
            "bank",
            "pan",
            "account",
            "invoice",
            "statement",
            "tax",
            "salary",
            "credit",
            "debit",
            "balance",
            "amount",
            "rs.",
            "inr",
        ],

        "Medical": [
            "patient",
            "diagnosis",
            "doctor",
            "hospital",
            "prescription",
            "treatment",
            "health",
            "medical",
            "blood",
            "report",
            "clinic",
        ],

        "HR": [
            "employee",
            "resume",
            "designation",
            "joining",
            "performance",
            "department",
            "appraisal",
            "salary",
            "pf",
            "experience",
        ],

        "Legal": [
            "agreement",
            "contract",
            "clause",
            "party",
            "court",
            "jurisdiction",
            "affidavit",
            "witness",
            "legal",
            "terms",
        ],

        "Supply Chain": [
            "shipment",
            "logistics",
            "freight",
            "warehouse",
            "inventory",
            "supplier",
            "manifest",
            "tracking",
            "distributor",
            "consignment",
            "bill of lading",
            "vendor",
            "dispatch",
        ],

        "Commerce": [
            "order",
            "cart",
            "e-commerce",
            "ecommerce",
            "checkout",
            "transaction",
            "merchant",
            "customer",
            "retail",
            "purchase",
            "sku",
            "payment",
            "fulfillment",
            "buyer",
            "seller",
        ],
    }

    # ------------------------------------------------------------------
    # Compliance rule mapping
    # ------------------------------------------------------------------
    COMPLIANCE_RULE_SETS: Dict[str, str] = {
        "Financial": "DPDP_ACT_2025_RULES",
        "Medical": "DPDP_ACT_2025_RULES",
        "HR": "DPDP_ACT_2025_RULES",
        "Legal": "DPDP_ACT_2025_RULES",
        "Supply Chain": "DPDP_ACT_2025_RULES",
        "Commerce": "DPDP_ACT_2025_RULES",
        "General": "STANDARD_PRIVACY_RULES",
    }

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------
    MIN_EVIDENCE_HITS = 1
    MANUAL_REVIEW_CONFIDENCE_THRESHOLD = 0.70
    AMBIGUITY_MARGIN = 0.15

    def classify_document(self, text: str) -> Dict[str, Any]:
        """
        Classifies the supplied document text.

        Returns:
            {
                "category": str,
                "confidence_score": float,
                "compliance_rule_set": str,
                "requires_manual_override": bool,
                "category_scores": Dict[str, int],
                "matched_keywords": Dict[str, list[str]]
            }
        """

        # --------------------------------------------------------------
        # Validate input
        # --------------------------------------------------------------
        if not text or not text.strip():
            return {
                "category": "General",
                "confidence_score": 0.0,
                "compliance_rule_set": self.COMPLIANCE_RULE_SETS["General"],
                "requires_manual_override": True,
                "category_scores": {
                    category: 0 for category in self.CATEGORIES
                },
                "matched_keywords": {
                    category: [] for category in self.CATEGORIES
                },
            }

        text_lower = text.lower()

        # --------------------------------------------------------------
        # Calculate keyword scores
        # --------------------------------------------------------------
        scores: Dict[str, int] = {}
        matched_keywords: Dict[str, list[str]] = {}

        for category, keywords in self.CATEGORIES.items():

            category_score = 0
            category_matches = []

            for keyword in keywords:

                # Escape keyword so special characters such as "."
                # in "rs." are treated literally.
                escaped_keyword = re.escape(keyword.lower())

                # Word-boundary matching.
                #
                # Example:
                # "bank" matches "bank account"
                # but not "banking".
                pattern = rf"\b{escaped_keyword}\b"

                matches = re.findall(pattern, text_lower)

                if matches:
                    category_score += len(matches)
                    category_matches.append(keyword)

            scores[category] = category_score
            matched_keywords[category] = category_matches

        # --------------------------------------------------------------
        # No evidence -> General
        # --------------------------------------------------------------
        total_hits = sum(scores.values())

        if total_hits < self.MIN_EVIDENCE_HITS:

            return {
                "category": "General",
                "confidence_score": 0.0,
                "compliance_rule_set": self.COMPLIANCE_RULE_SETS["General"],
                "requires_manual_override": True,
                "category_scores": scores,
                "matched_keywords": matched_keywords,
            }

        # --------------------------------------------------------------
        # Rank categories
        # --------------------------------------------------------------
        ranked_categories = sorted(
            scores.items(),
            key=lambda item: item[1],
            reverse=True
        )

        top_category, top_score = ranked_categories[0]
        second_score = (
            ranked_categories[1][1]
            if len(ranked_categories) > 1
            else 0
        )

        # --------------------------------------------------------------
        # Calculate confidence
        # --------------------------------------------------------------
        #
        # Primary signal:
        #
        #     top_score / total_hits
        #
        # This gives the proportion of evidence supporting the
        # winning category.
        #
        dominance = top_score / total_hits

        # Evidence strength:
        #
        # More matching keywords should increase confidence, but we
        # cap this contribution so huge documents don't automatically
        # become 100% confident.
        evidence_strength = min(top_score / 10.0, 1.0)

        # Combine dominance and evidence.
        confidence = (
            0.70 * dominance
            + 0.30 * evidence_strength
        )

        confidence = round(
            min(max(confidence, 0.0), 0.98),
            2
        )

        # --------------------------------------------------------------
        # Detect ambiguity
        # --------------------------------------------------------------
        #
        # Example:
        #
        # Financial = 5
        # HR        = 4
        #
        # Difference is small -> ambiguous.
        #
        if top_score > 0:
            relative_difference = (
                top_score - second_score
            ) / top_score
        else:
            relative_difference = 0.0

        ambiguous = relative_difference < self.AMBIGUITY_MARGIN

        # --------------------------------------------------------------
        # Manual review decision
        # --------------------------------------------------------------
        requires_manual_override = (
            confidence < self.MANUAL_REVIEW_CONFIDENCE_THRESHOLD
            or ambiguous
        )

        # --------------------------------------------------------------
        # Compliance rule set
        # --------------------------------------------------------------
        rule_set = self.COMPLIANCE_RULE_SETS.get(
            top_category,
            self.COMPLIANCE_RULE_SETS["General"]
        )

        return {
            "category": top_category,
            "confidence_score": confidence,
            "compliance_rule_set": rule_set,
            "requires_manual_override": requires_manual_override,
            "category_scores": scores,
            "matched_keywords": matched_keywords,
        }