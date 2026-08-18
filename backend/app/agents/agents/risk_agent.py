from typing import List, Dict, Any


class RiskAgent:
    """
    3. Risk Agent (SRS FR-3.1 - 3.3):
    Computes privacy risk score and category (High, Medium, Low) based on PII entity types,
    entity count, and document category. Routes High-risk documents to Human-in-the-Loop.
    """

    WEIGHTS = {
        "AADHAAR": 30,
        "PAN": 25,
        "FINANCIAL": 25,
        "MONEY": 20,
        "PHONE": 15,
        "EMAIL": 10,
        "NAME": 10,
        "DATE": 5,
        "ADDRESS": 15,
        "CUSTOM": 10
    }

    CATEGORY_WEIGHTS = {
        "Medical": 1.5,
        "Financial": 1.4,
        "Commerce": 1.3,
        "Supply Chain": 1.25,
        "HR": 1.2,
        "Legal": 1.1,
        "General": 1.0
    }

    def evaluate_risk(self, document_category: str, detected_entities: List[Dict[str, Any]]) -> Dict[str, Any]:
        base_score = 0
        type_counts = {}

        for ent in detected_entities:
            label = (ent.get("label") or "CUSTOM").upper()
            weight = self.WEIGHTS.get(label, 10)
            base_score += weight
            type_counts[label] = type_counts.get(label, 0) + 1

        multiplier = self.CATEGORY_WEIGHTS.get(document_category, 1.0)
        final_score = round(min(100.0, base_score * multiplier), 1)

        if final_score > 60:
            risk_category = "High"
            route_to_hitl = True
        elif final_score >= 30:
            risk_category = "Medium"
            route_to_hitl = False
        else:
            risk_category = "Low"
            route_to_hitl = False

        return {
            "risk_score": final_score,
            "risk_category": risk_category,
            "route_to_hitl": route_to_hitl,
            "entity_type_counts": type_counts,
            "rule_version": "2.0.0-SRS"
        }
