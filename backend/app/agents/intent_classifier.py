"""
PrivacyShieldAI - Intent Classifier Module
Classifies user queries into specialized document intelligence intents:
- summary
- analysis
- question
- compliance
- risk
- executive_summary
- comparison
- pii_explanation

Falls back gracefully to 'question' when query intent is ambiguous or low-confidence.
"""

import re
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional


@dataclass
class IntentResult:
    intent: str
    confidence: float
    reasoning: str
    matched_keywords: List[str] = field(default_factory=list)


class IntentClassifier:
    """
    Fast, deterministic intent classification engine using weighted multi-phrase matching,
    regex patterns, and query structure analysis.
    """

    # Keyword rules and weights for each intent
    INTENT_RULES: Dict[str, List[Tuple[str, float]]] = {
        "executive_summary": [
            (r"\bexecutive summary\b", 1.0),
            (r"\bexec summary\b", 1.0),
            (r"\bhigh level summary\b", 0.9),
            (r"\bbriefing for management\b", 0.9),
            (r"\bmanagement summary\b", 0.9),
        ],
        "summary": [
            (r"\bsummariz(e|ing|ation)\b", 0.95),
            (r"\bsummaris(e|ing|ation)\b", 0.95),
            (r"\bsummary\b", 0.90),
            (r"\boverview\b", 0.80),
            (r"\bsynopsis\b", 0.85),
            (r"\btl;?dr\b", 0.90),
            (r"\bdescribe the document\b", 0.85),
            (r"\bexplain this document\b", 0.85),
            (r"\btell me about this document\b", 0.85),
            (r"\bwhat is in the document\b", 0.85),
            (r"\bwhat is in this document\b", 0.85),
            (r"\bwhat does the document contain\b", 0.85),
            (r"\bwhat is this document about\b", 0.85),
            (r"\bgive me a summary\b", 0.90),
            (r"\bkey takeaways\b", 0.75),
            (r"\bbriefly explain\b", 0.70),
        ],
        "compliance": [
            (r"\bdpdp\b", 0.95),
            (r"\bcompliant\b", 0.90),
            (r"\bcompliance\b", 0.90),
            (r"\bgdpr\b", 0.90),
            (r"\bregulatory\b", 0.80),
            (r"\bprivacy policy\b", 0.75),
            (r"\bis this document compliant\b", 0.95),
            (r"\bdata protection act\b", 0.90),
            (r"\blegal compliance\b", 0.85),
        ],
        "analysis": [
            (r"\banalyz(e|ing|is)\b", 0.95),
            (r"\binsights?\b", 0.80),
            (r"\bbreakdown\b", 0.80),
            (r"\bevaluat(e|ion)\b", 0.80),
            (r"\bexamin(e|ation)\b", 0.75),
            (r"\baudit document\b", 0.85),
            (r"\bdocument structure\b", 0.70),
            (r"\bdeep dive\b", 0.80),
        ],
        "risk": [
            (r"\brisk[s]?\b", 0.90),
            (r"\bprivacy risk\b", 0.95),
            (r"\bsecurity risk\b", 0.95),
            (r"\bvulnerability\b", 0.90),
            (r"\bthreat[s]?\b", 0.85),
            (r"\bexposure\b", 0.80),
            (r"\brisk assessment\b", 0.95),
        ],
        "comparison": [
            (r"\bcompar(e|ison|ing)\b", 0.95),
            (r"\bdiffer(ence|ent|s)?\b", 0.80),
            (r"\bversus\b", 0.90),
            (r"\bvs\.?\b", 0.85),
            (r"\bsimilarities\b", 0.80),
        ],
        "pii_explanation": [
            (r"\bpii\b", 0.85),
            (r"\bmasked token[s]?\b", 0.90),
            (r"\bsensitive data\b", 0.80),
            (r"\bwhat pii\b", 0.90),
            (r"\bpersonal information\b", 0.75),
        ],
        "question": [
            (r"\bwhat is\b", 0.70),
            (r"\bwho is\b", 0.70),
            (r"\bwhere is\b", 0.70),
            (r"\bwhen (did|was|is)\b", 0.70),
            (r"\bhow (much|many|does)\b", 0.70),
            (r"\bfind the\b", 0.75),
            (r"\blookup\b", 0.75),
            (r"\bsearch for\b", 0.70),
        ],
    }

    @classmethod
    def classify(cls, query: str) -> IntentResult:
        """
        Classifies a user query string into an IntentResult.
        Falls back to 'question' with 0.50 confidence if no strong match found.
        """
        if not query or not query.strip():
            return IntentResult(
                intent="question",
                confidence=0.5,
                reasoning="Empty query provided; defaulted to question.",
                matched_keywords=[]
            )

        q_clean = query.strip().lower()

        scores: Dict[str, float] = {}
        matched_map: Dict[str, List[str]] = {}

        for intent, rules in cls.INTENT_RULES.items():
            intent_score = 0.0
            matched_keywords = []
            for pattern, weight in rules:
                matches = re.findall(pattern, q_clean, flags=re.IGNORECASE)
                if matches:
                    intent_score = max(intent_score, weight)
                    matched_keywords.append(pattern.replace(r"\b", "").replace(r"\?", ""))

            if intent_score > 0:
                scores[intent] = intent_score
                matched_map[intent] = matched_keywords

        if not scores:
            return IntentResult(
                intent="question",
                confidence=0.50,
                reasoning="No intent keywords matched; default QA fallback applied.",
                matched_keywords=[]
            )

        # Pick top scoring intent
        best_intent = max(scores, key=lambda k: scores[k])
        best_score = scores[best_intent]

        # Check for ambiguity (e.g. if top score is < 0.60, fallback to question)
        if best_score < 0.60:
            return IntentResult(
                intent="question",
                confidence=best_score,
                reasoning=f"Low confidence ({best_score:.2f}) for '{best_intent}'; falling back to QA.",
                matched_keywords=matched_map.get(best_intent, [])
            )

        return IntentResult(
            intent=best_intent,
            confidence=round(best_score, 2),
            reasoning=f"Detected '{best_intent}' intent with confidence {best_score:.2f}.",
            matched_keywords=matched_map.get(best_intent, [])
        )
