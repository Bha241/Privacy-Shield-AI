"""
PrivacyShieldAI - Context Builder Module (v3.0 Multi-Strategy Context Engine)
Builds intent-aware document context blocks supporting multiple context strategies:
- FULL_DOCUMENT: Returns complete document text directly from DocumentCache/doc_texts (bypasses vector search, confidence=high).
- SEMANTIC_RETRIEVAL: Target vector search for single-fact questions.
- HYBRID: Retrieves vector chunks and expands surrounding chunk text windows for complex multi-fact queries.
"""

import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

try:
    from app.agents.document_cache import document_cache
except ImportError:
    from pii_detector.document_cache import document_cache


@dataclass
class ContextBuildResult:
    context_block: str
    retrieved_chunks: List[Dict[str, Any]]
    intent: str
    top_k_used: int
    total_characters: int
    is_full_document: bool = False
    retrieval_confidence: str = "high"  # "high", "medium", or "low"
    source_attributions: List[str] = field(default_factory=list)
    context_strategy_used: str = "FULL_DOCUMENT"


class ContextBuilder:
    """
    Constructs optimized context blocks tailored to query intent and orchestration strategies.
    """

    DEFAULT_TOP_K_MAP = {
        "summary": 30,
        "executive_summary": 30,
        "analysis": 20,
        "compliance": 20,
        "risk": 15,
        "comparison": 15,
        "pii_explanation": 8,
        "question": 5,
    }

    MAX_CONTEXT_CHARS = 25000  # Expand max token window (~6,000 tokens)

    @classmethod
    def get_top_k_for_intent(cls, intent: str, requested_top_k: Optional[int] = None) -> int:
        """Determines retrieval depth (top_k) based on intent."""
        if requested_top_k and requested_top_k > 0:
            intent_default = cls.DEFAULT_TOP_K_MAP.get(intent, 5)
            return max(requested_top_k, intent_default)
        return cls.DEFAULT_TOP_K_MAP.get(intent, 5)

    @classmethod
    def deduplicate_chunks(cls, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Removes exact and high-substring overlap duplicate chunks."""
        unique_chunks = []
        seen_texts = set()

        for chunk in chunks:
            text = chunk.get("text", "").strip()
            if not text:
                continue

            fingerprint = re.sub(r"\s+", " ", text.lower())[:100]
            if fingerprint in seen_texts:
                continue

            is_dup = False
            words = set(re.findall(r"\w+", text.lower()))
            if words:
                for existing in unique_chunks:
                    ex_words = set(re.findall(r"\w+", existing.get("text", "").lower()))
                    if ex_words:
                        overlap = len(words & ex_words) / float(max(len(words), len(ex_words)))
                        if overlap > 0.85:
                            is_dup = True
                            break

            if not is_dup:
                seen_texts.add(fingerprint)
                unique_chunks.append(chunk)

        return unique_chunks

    @classmethod
    def rerank_chunks(
        cls,
        chunks: List[Dict[str, Any]],
        query: str,
        intent: str
    ) -> List[Dict[str, Any]]:
        """Reranks retrieved chunks based on query term density and position."""
        if not chunks:
            return []

        q_words = set(re.findall(r"\w+", query.lower())) - {
            "what", "is", "the", "a", "an", "of", "in", "to", "for", "and", "or", "please", "tell", "me", "about", "this", "document"
        }

        scored = []
        for idx, chunk in enumerate(chunks):
            text = chunk.get("text", "")
            chunk_words = set(re.findall(r"\w+", text.lower()))

            match_score = len(q_words & chunk_words) if q_words else 0
            position_score = max(0.0, 1.0 - (idx * 0.05))

            intent_boost = 0.0
            if intent in ["summary", "executive_summary", "analysis"] and len(text) > 200:
                intent_boost = 0.5

            total_score = (match_score * 2.0) + position_score + intent_boost
            scored.append((total_score, idx, chunk))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item[2] for item in scored]

    @classmethod
    def build_context(
        cls,
        intent: str,
        query: str,
        doc_texts: Dict[str, str],
        document_id: Optional[str] = None,
        document_name: Optional[str] = None,
        vector_store_manager: Optional[Any] = None,
        top_k: Optional[int] = None,
        context_strategy: Optional[str] = None
    ) -> ContextBuildResult:
        """
        Builds document context using the requested strategy:
        - FULL_DOCUMENT: Serves entire cached document text without vector search (confidence=high).
        - HYBRID: Vector search + adjacent chunk expansion.
        - SEMANTIC_RETRIEVAL: Target vector search.
        """
        top_k_to_use = cls.get_top_k_for_intent(intent, top_k)

        if not document_id:
            return ContextBuildResult(
                context_block="No document context selected.",
                retrieved_chunks=[],
                intent=intent,
                top_k_used=top_k_to_use,
                total_characters=0,
                is_full_document=False,
                retrieval_confidence="low",
                source_attributions=[],
                context_strategy_used="NO_DOCUMENT",
            )

        # All retrieval is explicitly scoped to this one document.
        primary_document_id = document_id
        resolved_document_name = document_name or document_id

        # Retrieve full text from DocumentCache or fallback doc_texts
        full_doc_text = document_cache.get_full_text(primary_document_id) if document_cache else ""
        if not full_doc_text and doc_texts:
            full_doc_text = doc_texts.get(primary_document_id, "")

        strategy = context_strategy or ("FULL_DOCUMENT" if intent in ["summary", "executive_summary", "analysis", "compliance", "risk"] else "SEMANTIC_RETRIEVAL")
        document_level_query = (strategy == "FULL_DOCUMENT" or intent in ["summary", "executive_summary", "analysis", "compliance", "risk"])
        document_exists = bool(full_doc_text and full_doc_text.strip())

        # STRATEGY 1: FULL_DOCUMENT (Document-level query and document exists)
        if document_level_query and document_exists:
            if len(full_doc_text) > cls.MAX_CONTEXT_CHARS:
                chunk_len = cls.MAX_CONTEXT_CHARS // 3
                parts = [full_doc_text[i:i+chunk_len] for i in range(0, len(full_doc_text), chunk_len)]
                cleaned_full_text = "\n\n--- DOCUMENT SECTION ---\n\n".join(parts[:4])
            else:
                cleaned_full_text = full_doc_text

            return ContextBuildResult(
                context_block=cleaned_full_text,
                retrieved_chunks=[{"chunk_id": f"full_doc_{primary_document_id}", "text": cleaned_full_text, "document_id": primary_document_id, "document_name": resolved_document_name}],
                intent=intent,
                top_k_used=top_k_to_use,
                total_characters=len(cleaned_full_text),
                is_full_document=True,
                retrieval_confidence="high",
                source_attributions=[f"(Source: {resolved_document_name})"],
                context_strategy_used="FULL_DOCUMENT"
            )

        retrieved_chunks = []

        # Vector search for Fact / Hybrid queries
        if vector_store_manager:
            try:
                retrieved_chunks.extend(vector_store_manager.search_similar_chunks(
                    query_text=query,
                    document_id=primary_document_id,
                    top_k=top_k_to_use
                ))
                retrieved_chunks = [
                    c for c in retrieved_chunks
                    if c.get("document_id") == primary_document_id
                ]
            except Exception:
                retrieved_chunks = []

        if strategy == "HYBRID" and retrieved_chunks and document_exists:
            expanded = []
            for chk in retrieved_chunks:
                txt = chk.get("text", "")
                idx = full_doc_text.find(txt[:50]) if len(txt) > 50 else -1
                if idx >= 0:
                    start = max(0, idx - 300)
                    end = min(len(full_doc_text), idx + len(txt) + 300)
                    expanded.append({"chunk_id": chk.get("chunk_id"), "text": full_doc_text[start:end], "document_id": chk.get("document_id"), "document_name": chk.get("document_name")})
                else:
                    expanded.append(chk)
            retrieved_chunks = expanded

        deduped = cls.deduplicate_chunks(retrieved_chunks)
        reranked = cls.rerank_chunks(deduped, query, intent)

        selected_chunks = []
        current_len = 0
        for chk in reranked:
            t = chk.get("text", "")
            if current_len + len(t) > cls.MAX_CONTEXT_CHARS and selected_chunks:
                break
            selected_chunks.append(chk)
            current_len += len(t)

        # APPLY CRITICAL FALLBACK RULE
        if retrieved_chunks and selected_chunks:
            context_texts = [c.get("text", "") for c in selected_chunks if c.get("text")]
            context_block = "\n\n".join(context_texts)
            used_strategy = strategy
            is_full_doc = False
            confidence = "high"
        elif document_exists:
            # STATE B: Document uploaded/cached, but vector search returned zero chunks -> Fallback to complete cached document
            context_block = full_doc_text[:cls.MAX_CONTEXT_CHARS]
            selected_chunks = [{"chunk_id": f"full_doc_fallback_{primary_document_id}", "text": context_block, "document_id": primary_document_id, "document_name": resolved_document_name}]
            used_strategy = "FULL_DOCUMENT_FALLBACK"
            is_full_doc = True
            confidence = "high"
        else:
            # STATE A: No document has been ingested
            context_block = "No selected document has been ingested."
            selected_chunks = []
            used_strategy = "NO_DOCUMENT"
            is_full_doc = False
            confidence = "low"

        source_attributions = []
        pages = set()
        for c in selected_chunks:
            ref = c.get("page_ref") or c.get("page")
            if ref:
                pages.add(str(ref))
        if pages:
            sorted_pages = sorted(list(pages), key=lambda x: int(x) if x.isdigit() else x)
            names = sorted({c.get("document_name", c.get("document_id", "document")) for c in selected_chunks})
            source_attributions.append(f"(Source: {', '.join(names)} · Page {', '.join(sorted_pages)})")
        else:
            source_attributions.append("(Source: Full Document)" if is_full_doc else "(Source: Document Excerpts)")

        return ContextBuildResult(
            context_block=context_block,
            retrieved_chunks=selected_chunks,
            intent=intent,
            top_k_used=top_k_to_use,
            total_characters=len(context_block),
            is_full_document=is_full_doc,
            retrieval_confidence=confidence,
            source_attributions=source_attributions,
            context_strategy_used=used_strategy
        )
