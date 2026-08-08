"""
PrivacyShieldAI - Document Orchestrator Module
Determines context strategy (FULL_DOCUMENT vs SEMANTIC_RETRIEVAL / HYBRID) BEFORE retrieval is performed.
Bypasses vector search completely for document-level queries (summaries, overviews, 'what is in the document', etc.).
"""

import re
import logging
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class OrchestrationPlan:
    query_scope: str  # "DOCUMENT_LEVEL" or "FACT_LEVEL"
    context_strategy: str  # "FULL_DOCUMENT", "SEMANTIC_RETRIEVAL", or "HYBRID"
    bypass_vector_search: bool
    reasoning: str


class DocumentOrchestrator:
    """
    Intelligent Context Orchestration Engine.
    Prevents weak vector search on generic document-level questions by bypassing retrieval
    and loading full document text directly from DocumentCache.
    """

    DOCUMENT_LEVEL_PATTERNS = [
        r"\b(summariz\w*|summaris\w*|summary|overview|synopsis|tl;?dr)\b",
        r"\bwhat is (in |inside |this |the )?(this |the )?doc(ument)?\b",
        r"\bwhat is in (this|the) (doc|document|file)\b",
        r"\bwhat is this (doc|document|file|invoice|contract|report|form|agreement)\b",
        r"\bwhat does (this|the) (doc|document|file) (say|contain|cover)\b",
        r"\b(tell me about|explain|describe) (this|the)?\s*(doc|document|file)?\b",
        r"\bexecutive summary\b",
        r"\bbusiness summary\b",
        r"\blegal summary\b",
        r"\b(analyz\w*|analys\w*)\b",
        r"\banalysis of (this|the)?\s*(doc|document|file)?\b",
        r"\bcompliance (review|check|evaluation)?\b",
        r"\brisk (assessment|analysis|evaluation)?\b",
        r"\bgive me (a |an )?(overview|summary|breakdown)\b",
    ]

    FACT_LEVEL_PATTERNS = [
        r"\b(pan|gstin|aadhaar|ssn|invoice amount|total amount|payable|supplier|vendor|phone|email|due date)\b",
        r"\bwhat is the (pan|gstin|amount|total|vendor|supplier|due date|phone|email)\b",
        r"\bwho is the (supplier|vendor|client|patient|employee)\b",
    ]

    @classmethod
    def orchestrate(
        cls,
        query: str,
        intent: str = "question",
        has_active_document: bool = True
    ) -> OrchestrationPlan:
        """
        Determines whether query is DOCUMENT_LEVEL (uses FULL_DOCUMENT strategy, bypassing vector search)
        or FACT_LEVEL (uses SEMANTIC_RETRIEVAL or HYBRID).
        """
        if not query or not query.strip():
            return OrchestrationPlan(
                query_scope="DOCUMENT_LEVEL",
                context_strategy="FULL_DOCUMENT",
                bypass_vector_search=True,
                reasoning="Empty query defaulted to FULL_DOCUMENT orchestration."
            )

        q_clean = query.strip().lower()

        # 1. Intent explicit override
        if intent in ["summary", "executive_summary", "analysis", "compliance", "risk"]:
            plan = OrchestrationPlan(
                query_scope="DOCUMENT_LEVEL",
                context_strategy="FULL_DOCUMENT",
                bypass_vector_search=True,
                reasoning=f"Intent '{intent}' requires complete document context."
            )
            logger.info(f"[ORCHESTRATOR] Query: '{query}' -> Scope: {plan.query_scope} | Strategy: {plan.context_strategy} | Bypass Vector: True")
            return plan

        # 2. Check for explicit DOCUMENT_LEVEL query patterns
        is_doc_level = any(re.search(pattern, q_clean, flags=re.IGNORECASE) for pattern in cls.DOCUMENT_LEVEL_PATTERNS)
        if is_doc_level:
            plan = OrchestrationPlan(
                query_scope="DOCUMENT_LEVEL",
                context_strategy="FULL_DOCUMENT",
                bypass_vector_search=True,
                reasoning="Query matched document-level overview pattern. Bypassing vector search."
            )
            logger.info(f"[ORCHESTRATOR] Query: '{query}' -> Scope: {plan.query_scope} | Strategy: {plan.context_strategy} | Bypass Vector: True")
            return plan

        # 3. Check for specific FACT_LEVEL query patterns
        is_fact_level = any(re.search(pattern, q_clean, flags=re.IGNORECASE) for pattern in cls.FACT_LEVEL_PATTERNS)
        if is_fact_level:
            plan = OrchestrationPlan(
                query_scope="FACT_LEVEL",
                context_strategy="SEMANTIC_RETRIEVAL",
                bypass_vector_search=False,
                reasoning="Targeted fact query suitable for vector search."
            )
            logger.info(f"[ORCHESTRATOR] Query: '{query}' -> Scope: {plan.query_scope} | Strategy: {plan.context_strategy} | Bypass Vector: False")
            return plan

        # 4. Default comparison intent to HYBRID
        if intent == "comparison":
            plan = OrchestrationPlan(
                query_scope="FACT_LEVEL",
                context_strategy="HYBRID",
                bypass_vector_search=False,
                reasoning="Comparison query requiring HYBRID search (vector search + chunk expansion)."
            )
            logger.info(f"[ORCHESTRATOR] Query: '{query}' -> Scope: {plan.query_scope} | Strategy: {plan.context_strategy} | Bypass Vector: False")
            return plan

        # 5. Default fallback to SEMANTIC_RETRIEVAL for specific questions
        plan = OrchestrationPlan(
            query_scope="FACT_LEVEL",
            context_strategy="SEMANTIC_RETRIEVAL",
            bypass_vector_search=False,
            reasoning="Default fact question strategy."
        )
        logger.info(f"[ORCHESTRATOR] Query: '{query}' -> Scope: {plan.query_scope} | Strategy: {plan.context_strategy} | Bypass Vector: False")
        return plan
