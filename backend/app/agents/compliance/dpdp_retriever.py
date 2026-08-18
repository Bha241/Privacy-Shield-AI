"""
DPDP Regulatory Retriever for PrivacyShield AI.

Provides semantic and keyword retrieval over DPDP statutory corpus:
- Section-level chunks from DPDP Act 2023
- Rule-level technical safeguard provisions from DPDP Rules 2025

Supports:
- Vector retrieval over collection `dpdp_regulations` (if vector store available)
- Deterministic local TF-IDF / BM25 fallback retrieval (if offline or database unavailable)
- Event type to query intent mapping
"""

import json
import re
import math
from pathlib import Path
from typing import List, Dict, Any, Optional

from .dpdp_schemas import DPDPClause

CORPUS_DIR = Path(__file__).resolve().parent / "dpdp_corpus"


class DPDPRegulationsRetriever:
    """
    Retrieves relevant DPDP statutory clauses and technical rules for compliance events.
    """

    def __init__(self, corpus_dir: Optional[Path] = None):
        self.corpus_dir = corpus_dir or CORPUS_DIR
        self._clauses_cache: List[DPDPClause] = []
        self._load_corpus()

    def _load_corpus(self) -> None:
        """Loads all statutory and rule chunks from the JSONL corpus files."""
        self._clauses_cache = []
        corpus_files = [
            self.corpus_dir / "sample_act_chunks.jsonl",
            self.corpus_dir / "sample_rules_chunks.jsonl",
        ]

        for filepath in corpus_files:
            if not filepath.exists():
                continue
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        self._clauses_cache.append(
                            DPDPClause(
                                clause_id=data.get("clause_id", "UNKNOWN"),
                                title=data.get("title", ""),
                                text=data.get("text", ""),
                                source=data.get("source", "DPDP Act 2023"),
                                tags=data.get("tags", []),
                                metadata=data.get("metadata", {})
                            )
                        )
                    except Exception:
                        pass

    def map_event_to_query(self, event_type: str, triggered_rules: Optional[List[str]] = None) -> str:
        """
        Maps a compliance event type and triggered violations to an optimal semantic retrieval query.
        """
        base_mappings = {
            "CLOUD_TRANSMISSION": "reasonable security safeguards masked transfer cloud transmission tokenization encryption Section 8 5 Rule 6 1 a",
            "DEMASKING": "purpose limitation access control authorization de-masking original identifiers Section 6 Rule 6 1 c",
            "RETENTION": "data retention erasure automated purge lifecycle limitation Section 8 7 Rule 8",
            "CHILD_DATA": "children personal data minor verifiable parental guardian consent Section 9 Rule 10",
            "AUDIT_LOG": "immutable audit logging accountability record keeping traceability Section 8 4 Rule 12",
            "DOCUMENT_PROCESSING": "notice consent lawful grounds processing personal data Section 4 Section 5 Rule 3",
        }

        query = base_mappings.get(event_type.upper(), "reasonable security safeguards data protection obligations")

        # Enrich query with specific violation context if available
        if triggered_rules:
            extra_terms = " ".join(triggered_rules)
            query = f"{query} {extra_terms}"

        return query

    def _tokenize(self, text: str) -> List[str]:
        """Simple lower-case word tokenizer."""
        return [w.lower() for w in re.findall(r"\b\w+\b", text) if len(w) > 2]

    def _fallback_keyword_retrieve(self, query: str, top_k: int = 4) -> List[DPDPClause]:
        """
        Deterministic TF-IDF/BM25-style keyword retrieval when vector store is unavailable.
        """
        if not self._clauses_cache:
            self._load_corpus()

        q_tokens = set(self._tokenize(query))
        if not q_tokens or not self._clauses_cache:
            return self._clauses_cache[:top_k]

        scored_clauses: List[tuple[float, DPDPClause]] = []

        for clause in self._clauses_cache:
            clause_content = f"{clause.title} {clause.text} {' '.join(clause.tags)} {clause.clause_id}".lower()
            clause_tokens = self._tokenize(clause_content)
            
            # Compute token overlap & tag matching bonus
            overlap = sum(1 for t in q_tokens if t in clause_content)
            tag_matches = sum(2 for tag in clause.tags if tag.lower() in q_tokens)
            
            score = (overlap + tag_matches) / (len(q_tokens) + 1e-5)

            if score > 0.0:
                scored_clause = DPDPClause(
                    clause_id=clause.clause_id,
                    title=clause.title,
                    text=clause.text,
                    source=clause.source,
                    tags=clause.tags,
                    score=round(float(score), 4),
                    metadata=clause.metadata
                )
                scored_clauses.append((score, scored_clause))

        # Sort by score descending
        scored_clauses.sort(key=lambda x: x[0], reverse=True)
        results = [c for _, c in scored_clauses[:top_k]]

        # If no specific matches, return top default safeguards
        if not results:
            results = self._clauses_cache[:top_k]

        return results

    def retrieve(self, query: str, top_k: int = 4) -> List[DPDPClause]:
        """
        Retrieves top_k DPDP regulatory clauses matching the query.
        Tries vector store first, falls back gracefully to local corpus index.
        """
        # Try vector store collection 'dpdp_regulations' if present
        try:
            from app.agents.db.vector_store import get_vector_store
            v_store = get_vector_store()
            if hasattr(v_store, "search") and callable(v_store.search):
                v_results = v_store.search(collection_name="dpdp_regulations", query=query, top_k=top_k)
                if v_results:
                    clauses = []
                    for r in v_results:
                        meta = r.get("metadata", {})
                        clauses.append(
                            DPDPClause(
                                clause_id=meta.get("clause_id", r.get("id", "DPDP_REG")),
                                title=meta.get("title", "Regulatory Clause"),
                                text=r.get("text", meta.get("text", "")),
                                source=meta.get("source", "DPDP Act 2023"),
                                tags=meta.get("tags", []),
                                score=round(float(r.get("score", 0.0)), 4),
                                metadata=meta
                            )
                        )
                    return clauses
        except Exception:
            pass

        # Fallback local index
        return self._fallback_keyword_retrieve(query, top_k=top_k)
