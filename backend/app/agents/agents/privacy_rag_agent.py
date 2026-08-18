"""
PrivacyShieldAI - Privacy-Preserving RAG Agent (v3.0 AI Document Analyst Architecture)
Integrates:
- DocumentOrchestrator: Categorizes queries into DOCUMENT_LEVEL vs FACT_LEVEL and chooses context strategies (FULL_DOCUMENT, SEMANTIC_RETRIEVAL, HYBRID).
- DocumentCache: In-memory store for instant full document retrieval without vector search.
- DocumentClassifier: Classifies document types (MSA, Invoice, Medical Record, Onboarding, etc.) and assigns expert personas.
- PromptManager: Reasoning-oriented Chain-of-Thought prompts, dynamic summary modes, and rich few-shot library.
- IntentClassifier: Classifies user intent into specialized document analysis modes.
- ContextBuilder: Multi-strategy context expansion, strict document isolation, retrieval confidence, and citations.
- ResponseFormatter: Eliminates AI cliches, strips robotic labels, formats intent outputs, and performs quality self-reviews.
- LLMRouter: Multi-tier cascade generation across Groq Cloud, Local Qwen, Future Providers, and Smart Synthesis.
- PII Masking & De-masking: Zero raw PII leaves local environment.
"""

import os
import re
import time
import uuid
import logging
from typing import Optional, List, Dict, Any, Tuple, Union

from app.agents.observability import traceable

try:
    from groq import Groq
    HAS_GROQ_SDK = True
except ImportError:
    Groq = None
    HAS_GROQ_SDK = False

try:
    from app.agents.db.vector_store import vector_store_manager, generate_text_embedding
except ImportError:
    try:
        from pii_detector.db.vector_store import vector_store_manager, generate_text_embedding
    except ImportError:
        vector_store_manager = None
        generate_text_embedding = lambda text: [0.0] * 384

# Import modular AI Document Analyst & Orchestrator components
try:
    from app.agents.document_cache import document_cache
    from app.agents.document_orchestrator import DocumentOrchestrator
    from app.agents.document_classifier import DocumentClassifier
    from app.agents.prompt_manager import PromptManager
    from app.agents.intent_classifier import IntentClassifier
    from app.agents.context_builder import ContextBuilder
    from app.agents.response_formatter import ResponseFormatter
    from app.agents.llm_router import LLMRouter, MODEL_MAPPING
except ImportError:
    from pii_detector.document_cache import document_cache
    from pii_detector.document_orchestrator import DocumentOrchestrator
    from pii_detector.document_classifier import DocumentClassifier
    from pii_detector.prompt_manager import PromptManager
    from pii_detector.intent_classifier import IntentClassifier
    from pii_detector.context_builder import ContextBuilder
    from pii_detector.response_formatter import ResponseFormatter
    from pii_detector.llm_router import LLMRouter, MODEL_MAPPING

logger = logging.getLogger(__name__)


def _bounded_prompt_context(context: str) -> str:
    """Keep cloud prompt input bounded without discarding both document edges."""
    try:
        max_chars = max(8_000, int(os.getenv("PRIVACYSHIELD_MAX_PROMPT_CONTEXT_CHARS", "24000")))
    except ValueError:
        max_chars = 24_000
    if len(context) <= max_chars:
        return context

    head_chars = max_chars // 2
    tail_chars = max_chars - head_chars
    return (
        context[:head_chars]
        + "\n\n[Additional middle document content omitted to stay within the model input limit.]\n\n"
        + context[-tail_chars:]
    )


def _bounded_history(history: Optional[List[Dict[str, str]]]) -> Optional[List[Dict[str, str]]]:
    """Limit prior chat text so it cannot push a valid document prompt over budget."""
    if not history:
        return history
    try:
        max_chars = max(2_000, int(os.getenv("PRIVACYSHIELD_MAX_PROMPT_HISTORY_CHARS", "8000")))
    except ValueError:
        max_chars = 8_000

    kept: List[Dict[str, str]] = []
    used = 0
    for message in reversed(history):
        if not isinstance(message, dict) or message.get("role") not in {"user", "assistant"}:
            continue
        content = str(message.get("content", "")).strip()
        if not content:
            continue
        remaining = max_chars - used
        if remaining <= 0:
            break
        clipped = content[-remaining:]
        kept.append({"role": message["role"], "content": clipped})
        used += len(clipped)
    return list(reversed(kept))

QUERY_PII_PATTERNS = {
    "AADHAAR": r"\b[2-9]\d{3}\s?\d{4}\s?\d{4}\b",
    "PAN": r"\b[A-Z]{5}\d{4}[A-Z]{1}\b",
    "EMAIL": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
    "PHONE": r"\b(?:\+91[\-\s]?)?[6-9]\d{9}\b",
    "CREDIT_CARD": r"\b(?:\d[ -]*?){13,16}\b",
    "GSTIN": r"\b\d{2}[A-Z]{5}\d{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}\b",
    "UPI": r"\b[\w.\-]+@[\w.\-]+\b",
    "NAME": r"\b(?:Coordinator|Patient|Physician|Doctor|Officer|Accountant|Name|Holder|Signatory|Representative|Contact|User|Client|Manager|Agent)[:\s]{1,4}([A-Z][a-zA-Z\.\'\-]+\s+[A-Z][a-zA-Z\.\'\-]+(?:\s+[A-Z][a-zA-Z\.\'\-]+)?)",
}


def mask_text_pii(text: str, prefix: str = "PII") -> Tuple[str, Dict[str, str]]:
    """Sanitizes text by replacing PII pattern matches with privacy tokens."""
    if not text:
        return text, {}

    masked_str = text
    mapping = {}
    counter = {}

    for entity_type, pattern in QUERY_PII_PATTERNS.items():
        matches = list(re.finditer(pattern, masked_str, flags=re.IGNORECASE))
        for m in matches:
            val = m.group(m.lastindex).strip() if m.lastindex else m.group(0).strip()
            if not val or len(val) < 3:
                continue

            counter[entity_type] = counter.get(entity_type, 0) + 1
            token = (
                f"<QUERY_{entity_type}_{counter[entity_type]}>"
                if prefix == "Q"
                else f"<{entity_type}_{counter[entity_type]}>"
            )
            masked_str = masked_str.replace(val, token, 1)
            mapping[token] = val

    return masked_str, mapping


def mask_query_pii(query: str) -> Tuple[str, Dict[str, str]]:
    """Sanitizes user query string."""
    return mask_text_pii(query, prefix="Q")


def demask_text(text: str, mapping: Dict[str, str]) -> str:
    """Restores original PII values back into LLM responses with fuzzy token matching."""
    if not mapping or not text:
        return text

    demasked = text
    for token, original in sorted(mapping.items(), key=lambda x: len(x[0]), reverse=True):
        if token in demasked:
            demasked = demasked.replace(token, str(original))
        else:
            core = token.strip("<>[]()").replace(r"\_", "_")
            clean = re.escape(core).replace(r"\_", "_").replace("_", r"[\s_\-]*")
            pattern = re.compile(rf"[<\[(]?{clean}[>\])]?", re.IGNORECASE)
            demasked = pattern.sub(str(original), demasked)

    return demasked


class PrivacyRAGAgent:
    """
    Production Privacy-Preserving AI Document Analyst.
    - Zero raw PII transmitted to Cloud LLMs.
    - Document Orchestrator: Smart routing between DOCUMENT_LEVEL (Full Document) and FACT_LEVEL (Vector/Hybrid).
    - Document Cache: In-memory cache for instant document-level summaries without vector search.
    - Automatic Document Classification & Persona Assignment.
    - Multi-intent support: Summary, Analysis, Compliance (DPDP), Risk, Executive Summary, QA, Comparison.
    - Multi-tier LLM generation cascade: Groq Cloud -> Local Qwen -> Smart Synthesis Fallback.
    """

    def __init__(
        self,
        model_name: Optional[str] = None,
        groq_api_key: Optional[str] = None,
        **kwargs
    ):
        configured_model = model_name or os.getenv("GROQ_MODEL", os.getenv("DEFAULT_CLOUD_MODEL", "openai/gpt-oss-120b"))
        self.model_name = MODEL_MAPPING.get(configured_model, configured_model)
        self.groq_api_key = groq_api_key or os.getenv("GROQ_API_KEY")
        self.current_document_id = None
        self.file_name = ""
        self.doc_mappings: Dict[str, Dict[str, str]] = {}
        self.doc_texts: Dict[str, str] = {}
        self.doc_classifications: Dict[str, Any] = {}
        self.file_names_by_doc_id: Dict[str, str] = {}
        self.masked_result = None

        # Initialize core AI Document Analyst & Orchestrator sub-modules
        self.document_cache = document_cache
        self.document_orchestrator = DocumentOrchestrator()
        self.document_classifier = DocumentClassifier()
        self.prompt_manager = PromptManager()
        self.intent_classifier = IntentClassifier()
        self.context_builder = ContextBuilder()
        self.response_formatter = ResponseFormatter()
        self.llm_router = LLMRouter(default_model=self.model_name)
        self.file_name_to_doc_id: Dict[str, str] = {}

    def resolve_document_id(self, document_id: Optional[str] = None) -> str:
        """
        Resolves provided document_id or file_name to canonical document_id stored in doc_texts and document_cache.
        """
        if document_id:
            if hasattr(self, "file_name_to_doc_id") and document_id in self.file_name_to_doc_id:
                return self.file_name_to_doc_id[document_id]
            if document_id in self.doc_texts:
                return document_id
            if self.document_cache and self.document_cache.has_document(document_id):
                return document_id
    def ingest_masked_text(
        self,
        masked_text: str,
        document_id: Optional[str] = None,
        file_name: Optional[str] = None
    ) -> bool:
        """Ingests masked document text into RAG cache and vector store."""
        return self.ingest_masked_result(
            masked_result=masked_text,
            file_name=file_name,
            document_id=document_id
        )

    def ingest_masked_result(
        self,
        masked_result: Any,
        file_name: Optional[str] = None,
        document_id: Optional[str] = None,
        chunk_size: int = 900,
        overlap: int = 120
    ) -> bool:
        """Ingests sanitized document text and mapping dictionary into cache, state, and vector store."""
        doc_id = document_id or f"doc_{uuid.uuid4().hex}"
        self.current_document_id = doc_id
        self.file_name = file_name or doc_id
        self.file_names_by_doc_id[doc_id] = self.file_name

        if not hasattr(self, "file_name_to_doc_id"):
            self.file_name_to_doc_id = {}
        self.file_name_to_doc_id[doc_id] = doc_id

        if hasattr(masked_result, "masked_text"):
            masked_text = masked_result.masked_text
            mapping = getattr(masked_result, "mapping", {}) or {}
        elif isinstance(masked_result, dict):
            masked_text = masked_result.get("masked_text", "")
            mapping = masked_result.get("mapping", {})
        else:
            masked_text = str(masked_result)
            mapping = {}

        # Token names remain readable and reset per document. Isolation is
        # provided by the document-keyed stores below, never by token text.
        scoped_mapping: Dict[str, str] = dict(mapping)
        scoped_text = masked_text

        self.doc_texts[doc_id] = scoped_text
        self.doc_mappings[doc_id] = scoped_mapping

        # Store in DocumentCache for instant document-level context assembly
        self.document_cache.store(
            document_id=doc_id,
            masked_text=scoped_text,
            mapping=scoped_mapping,
            file_name=self.file_name
        )

        assert len(self.doc_texts[doc_id]) > 0, f"Error: Ingested document text for {doc_id} is empty!"

        ingest_log = (
            f"DOCUMENT INGESTION\n"
            f"document_id={doc_id}\n"
            f"file_name={self.file_name}\n"
            f"masked_text_length={len(scoped_text)}\n"
            f"masked_text_lines={len(scoped_text.splitlines()) if scoped_text else 0}\n"
            f"mapping_count={len(scoped_mapping)}"
        )
        logger.info(ingest_log)
        print(ingest_log, flush=True)

        ingest_id_log = f"INGEST DOCUMENT ID:\n{doc_id}"
        logger.info(ingest_id_log)
        print(ingest_id_log, flush=True)

        # Perform automatic Document Type Classification & Persona Assignment
        cls_result = DocumentClassifier.classify(scoped_text)
        self.doc_classifications[doc_id] = cls_result

        chunks = self._chunk_text(scoped_text, chunk_size=chunk_size, overlap=overlap)

        if vector_store_manager:
            db_session = None
            try:
                try:
                    from app.agents.db.database import db_manager
                    db_session = db_manager.get_session()
                except Exception:
                    db_session = None
                for idx, chk in enumerate(chunks, start=1):
                    emb = generate_text_embedding(chk)
                    vector_store_manager.store_sanitized_chunk(
                        db_session=db_session,
                        document_id=doc_id,
                        document_name=self.file_name,
                        text=chk,
                        embedding_vector=emb,
                        page_ref=str(idx),
                        chunk_index=idx
                    )
            except Exception as e:
                logger.warning(f"Vector store chunk indexing notice: {e}")
            finally:
                if db_session:
                    db_session.close()

        logger.info(f"Ingested document {doc_id} ({cls_result.doc_type} / Persona: {cls_result.persona}) -> {len(chunks)} chunks")
        return True

    def _hydrate_document_state(self, document_id: str) -> bool:
        """Reload persisted text and mapping for one document after restart."""
        try:
            from app.agents.db.database import db_manager
            from pii_detector.db.models import DocumentModel
            import json
            with db_manager.get_session() as session:
                document = session.get(DocumentModel, document_id)
                if not document or not document.masked_text:
                    return False
                self.doc_texts[document_id] = document.masked_text
                self.doc_mappings[document_id] = json.loads(document.token_mapping_json or "{}")
                self.file_names_by_doc_id[document_id] = document.filename
                self.document_cache.store(
                    document_id=document_id,
                    masked_text=document.masked_text,
                    mapping=self.doc_mappings[document_id],
                    file_name=document.filename,
                )
                return True
        except Exception as exc:
            logger.warning("Document state hydration failed for %s: %s", document_id, exc)
            return False

    def _chunk_text(self, text: str, chunk_size: int = 450, overlap: int = 60) -> List[str]:
        """Splits document text into overlapping paragraph-aware chunks."""
        if not text:
            return []
        if len(text) <= chunk_size:
            return [text]

        paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]
        chunks = []
        current = ""

        for p in paragraphs:
            if len(current) + len(p) + 2 <= chunk_size:
                current = f"{current}\n\n{p}".strip()
            else:
                if current:
                    chunks.append(current)
                if len(p) > chunk_size:
                    sentences = re.split(r'(?<=[.!?])\s+', p)
                    sub = ""
                    for s in sentences:
                        if len(sub) + len(s) + 1 <= chunk_size:
                            sub = f"{sub} {s}".strip()
                        else:
                            if sub:
                                chunks.append(sub)
                            sub = s
                    current = sub
                else:
                    current = p

        if current:
            chunks.append(current)

        return chunks or [text]

    @traceable(
        name="privacyshield.rag.answer_query",
        run_type="chain",
        tags=["privacyshield", "rag", "pii-safe"],
    )
    def answer_query(
        self,
        user_query: str,
        document_id: Optional[str] = None,
        groq_api_key: Optional[str] = None,
        temperature: float = 0.15,
        max_tokens: int = 4096,
        top_p: float = 0.9,
        model_name: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
        top_k: int = 12,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Executes end-to-end AI Document Analyst query pipeline:
        1. Strict Document Scope Selection
        2. Query PII Masking
        3. Intent Classification
        4. Document Orchestration (DOCUMENT_LEVEL vs FACT_LEVEL strategy)
        5. Multi-Strategy Context Building
        6. Persona & CoT Prompt Assembly
        7. Multi-Tier LLM Generation Cascade
        8. Response Formatter & Quality Review Self-Correction
        9. PII Token De-masking
        """
        effective_doc_id = document_id or self.current_document_id
        if not effective_doc_id:
            raise ValueError("No document context selected. Select at least one ready document before chatting.")

        canonical_document_id = self.resolve_document_id(effective_doc_id)
        # Rehydrate only the explicitly selected documents after a backend
        # restart. Never hydrate or inspect the latest/other document.
        self._hydrate_document_state(canonical_document_id)
        if canonical_document_id not in self.doc_texts and not self.document_cache.has_document(canonical_document_id):
            if vector_store_manager and hasattr(vector_store_manager, "hydrate_document"):
                vector_store_manager.hydrate_document(canonical_document_id)
                selected_chunks = [chunk for chunk in vector_store_manager.chunks_cache if chunk.get("document_id") == canonical_document_id]
                selected_chunks.sort(key=lambda chunk: str(chunk.get("page_ref", "1")))
                if selected_chunks:
                    self.file_names_by_doc_id[canonical_document_id] = selected_chunks[0].get("document_name", canonical_document_id)
                    self.doc_texts[canonical_document_id] = "\n\n".join(chunk.get("text", "") for chunk in selected_chunks)
        if not canonical_document_id or (canonical_document_id not in self.doc_texts and not self.document_cache.has_document(canonical_document_id)):
            raise ValueError(f"Requested document context is unavailable: {canonical_document_id}")

        chat_id_log = f"CHAT DOCUMENT ID:\n{canonical_document_id}"
        logger.info(chat_id_log)
        print(chat_id_log, flush=True)

        # 1. Document Classification & Persona Lookup
        doc_text = self.document_cache.get_full_text(canonical_document_id) or self.doc_texts.get(canonical_document_id, "")
        cls_info = self.doc_classifications.get(canonical_document_id)
        if not cls_info:
            cls_info = DocumentClassifier.classify(doc_text)
            self.doc_classifications[canonical_document_id] = cls_info

        doc_type = cls_info.doc_type
        persona = cls_info.persona

        active_mapping: Dict[str, str] = dict(self.doc_mappings.get(canonical_document_id, {}))
        if self.document_cache.has_document(canonical_document_id):
            active_mapping.update(self.document_cache.get_mapping(canonical_document_id))

        # 2. Mask user query PII
        masked_query, query_mapping = mask_query_pii(user_query)

        # 3. Intent Classification
        intent_res = IntentClassifier.classify(masked_query)
        intent = intent_res.intent

        # 4. Document Orchestration (DOCUMENT_LEVEL vs FACT_LEVEL strategy selection)
        orchestration_plan = DocumentOrchestrator.orchestrate(
            query=masked_query,
            intent=intent,
            has_active_document=bool(doc_text)
        )

        # 5. Build context using selected orchestration strategy (FULL_DOCUMENT, SEMANTIC_RETRIEVAL, or HYBRID)
        context_res = ContextBuilder.build_context(
            intent=intent,
            query=masked_query,
            document_id=canonical_document_id,
            doc_texts=self.doc_texts,
            document_name=self.file_names_by_doc_id.get(canonical_document_id, canonical_document_id),
            vector_store_manager=vector_store_manager,
            top_k=top_k,
            context_strategy=orchestration_plan.context_strategy
        )
        context_block = context_res.context_block
        retrieved_chunks = context_res.retrieved_chunks
        retrieval_confidence = context_res.retrieval_confidence
        source_attributions = context_res.source_attributions

        # Log pipeline orchestration details
        cache_status = "HIT" if self.document_cache.has_document(canonical_document_id) else "MISS"
        chunks_count = 0 if context_res.is_full_document else len(retrieved_chunks)
        logger.info(
            f"[ORCHESTRATION PIPELINE] Intent: {intent.upper()} | "
            f"Strategy: {context_res.context_strategy_used} | "
            f"Chunks Retrieved: {chunks_count} | "
            f"Document Cache: {cache_status} | "
            f"Context Size: {len(context_block)} characters | "
            f"Confidence: {retrieval_confidence}"
        )

        # Safety net sanitization on retrieved context
        if context_block and context_block not in ["No matching document context found.", "No document has been ingested.", "No selected document has been ingested."]:
            context_block, _ = mask_text_pii(context_block, prefix="CTX")
        context_block = _bounded_prompt_context(context_block)

        # 6. Assemble chat messages with persona & reasoning prompts
        messages = PromptManager.build_messages(
            intent=intent,
            context=context_block,
            query=masked_query,
            doc_type=doc_type,
            persona=persona,
            history=_bounded_history(history)
        )

        # 7. Route generation to LLM (Groq -> Local Qwen -> Smart Synthesis)
        requested_model = model_name or self.model_name
        target_model = MODEL_MAPPING.get(requested_model, requested_model)
        active_api_key = groq_api_key or self.groq_api_key or os.getenv("GROQ_API_KEY")

        # VERIFY CONTEXT BEFORE LLM (REQUIRED LOGS)
        first_200 = context_block[:200] if context_block else ""
        last_200 = context_block[-200:] if context_block and len(context_block) > 200 else first_200
        context_lines = len(context_block.splitlines()) if context_block else 0
        document_cache_hit = "TRUE" if cache_status == "HIT" else "FALSE"
        retrieved_chunks_count = 0 if context_res.is_full_document else len(retrieved_chunks)

        llm_debug_log = (
            f"LLM CONTEXT DEBUG\n"
            f"document_id={canonical_document_id}\n"
            f"intent={intent}\n"
            f"context_strategy={context_res.context_strategy_used}\n"
            f"context_length={len(context_block)}\n"
            f"context_lines={context_lines}\n"
            f"retrieved_chunks={retrieved_chunks_count}\n"
            f"document_cache_hit={document_cache_hit}\n"
            f"provider=Groq\n"
            f"model={target_model}\n"
            f"context_head_200={first_200!r}\n"
            f"context_tail_200={last_200!r}"
        )
        logger.info(llm_debug_log)
        print(llm_debug_log, flush=True)

        llm_res = self.llm_router.generate(
            messages=messages,
            model_name=target_model,
            groq_api_key=active_api_key,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            intent=intent,
            query=masked_query,
            context=context_block
        )

        raw_masked_response = llm_res.content
        engine_used = llm_res.engine_used
        provider_used = getattr(llm_res, "provider_used", "Groq")
        routing_strategy = getattr(llm_res, "routing_strategy", "Cloud")
        fallback_reason = getattr(llm_res, "fallback_reason", None)
        latency_ms = getattr(llm_res, "latency_ms", 0)
        request_id = getattr(llm_res, "request_id", "")

        # 8. Quality Review Self-Correction & Response Formatting
        formatted_masked_response = ResponseFormatter.format_response(
            raw_text=raw_masked_response,
            intent=intent,
            query=user_query,
            confidence=retrieval_confidence
        )

        # Append source attributions for specific factual queries
        if source_attributions and intent in ["analysis", "compliance", "detailed_summary"] and not context_res.is_full_document:
            formatted_masked_response += f"\n\n_{source_attributions[0]}_"

        # 9. Demask PII tokens back to original values for the user
        final_answer = demask_text(formatted_masked_response, active_mapping)

        return {
            "query": user_query,
            "masked_query_used": masked_query,
            "masked_context": context_block,
            "masked_context_sent_to_cloud": context_block,
            "masked_response": formatted_masked_response,
            "cloud_llm_masked_response": formatted_masked_response,
            "unmasked_response": final_answer,
            "final_unmasked_answer": final_answer,
            "model": target_model,
            "model_used": engine_used,
            "provider_used": provider_used,
            "routing_strategy": routing_strategy,
            "fallback_reason": fallback_reason,
            "latency_ms": latency_ms,
            "request_id": request_id,
            "mapping": active_mapping,
            "file_name": self.file_names_by_doc_id.get(canonical_document_id, canonical_document_id),
            "document_id": canonical_document_id,
            "sources_retrieved": [
                f"{self.file_names_by_doc_id.get(c.get('document_id', ''), c.get('document_id', 'document'))} · p. {c.get('page_ref', c.get('page', '1'))}"
                for c in retrieved_chunks
            ],
            "privacy_guarantee": "Zero raw PII transmitted to Groq cloud API",
            "intent": intent,
            "intent_confidence": intent_res.confidence,
            "intent_reasoning": intent_res.reasoning,
            "query_scope": orchestration_plan.query_scope,
            "context_strategy_used": context_res.context_strategy_used,
            "bypassed_vector_search": orchestration_plan.bypass_vector_search,
            "doc_type": doc_type,
            "persona": persona,
            "retrieval_confidence": retrieval_confidence,
            "source_attributions": source_attributions,
        }

    def answer_query_stream(
        self,
        user_query: str,
        document_id: Optional[str] = None,
        groq_api_key: Optional[str] = None,
        temperature: float = 0.15,
        max_tokens: int = 1024,
        top_p: float = 0.9,
        model_name: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
        top_k: int = 4
    ):
        """Streaming execution pipeline returning Groq stream and context metadata."""
        api_key = groq_api_key or self.groq_api_key or os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("Groq API Key is missing. Please set GROQ_API_KEY environment variable or pass groq_api_key.")

        if not document_id:
            raise ValueError("No document context selected. Select at least one ready document before chatting.")
        canonical_document_id = self.resolve_document_id(document_id)
        self._hydrate_document_state(canonical_document_id)
        if not canonical_document_id or (canonical_document_id not in self.doc_texts and not self.document_cache.has_document(canonical_document_id)):
            raise ValueError(f"Requested document context is unavailable: {canonical_document_id}")

        chat_id_log = f"CHAT DOCUMENT ID:\n{canonical_document_id}"
        logger.info(chat_id_log)
        print(chat_id_log, flush=True)

        doc_text = self.document_cache.get_full_text(canonical_document_id) or self.doc_texts.get(canonical_document_id, "")
        cls_info = self.doc_classifications.get(canonical_document_id)
        if not cls_info:
            cls_info = DocumentClassifier.classify(doc_text)
            self.doc_classifications[canonical_document_id] = cls_info

        doc_type = cls_info.doc_type
        persona = cls_info.persona

        active_mapping: Dict[str, str] = dict(self.doc_mappings.get(canonical_document_id, {}))
        if self.document_cache.has_document(canonical_document_id):
            active_mapping.update(self.document_cache.get_mapping(canonical_document_id))

        masked_query, _ = mask_query_pii(user_query)

        intent_res = IntentClassifier.classify(masked_query)
        intent = intent_res.intent

        orchestration_plan = DocumentOrchestrator.orchestrate(
            query=masked_query,
            intent=intent,
            has_active_document=bool(doc_text)
        )

        context_res = ContextBuilder.build_context(
            intent=intent,
            query=masked_query,
            document_id=canonical_document_id,
            doc_texts=self.doc_texts,
            document_name=self.file_names_by_doc_id.get(canonical_document_id, canonical_document_id),
            vector_store_manager=vector_store_manager,
            top_k=top_k,
            context_strategy=orchestration_plan.context_strategy
        )
        context_block = context_res.context_block

        if context_block and context_block not in ["No matching document context found.", "No document has been ingested.", "No selected document has been ingested."]:
            context_block, _ = mask_text_pii(context_block, prefix="CTX")
        context_block = _bounded_prompt_context(context_block)

        messages = PromptManager.build_messages(
            intent=intent,
            context=context_block,
            query=masked_query,
            doc_type=doc_type,
            persona=persona,
            history=_bounded_history(history)
        )

        requested_model = model_name or self.model_name
        target_model = MODEL_MAPPING.get(requested_model, requested_model)

        first_200 = context_block[:200] if context_block else ""
        last_200 = context_block[-200:] if context_block and len(context_block) > 200 else first_200
        context_lines = len(context_block.splitlines()) if context_block else 0
        document_cache_hit = "TRUE" if self.document_cache.has_document(canonical_document_id) else "FALSE"
        retrieved_chunks_count = 0 if context_res.is_full_document else len(context_res.retrieved_chunks)

        llm_debug_log = (
            f"LLM CONTEXT DEBUG\n"
            f"document_id={canonical_document_id}\n"
            f"intent={intent}\n"
            f"context_strategy={context_res.context_strategy_used}\n"
            f"context_length={len(context_block)}\n"
            f"context_lines={context_lines}\n"
            f"retrieved_chunks={retrieved_chunks_count}\n"
            f"document_cache_hit={document_cache_hit}\n"
            f"provider=Groq\n"
            f"model={target_model}\n"
            f"context_head_200={first_200!r}\n"
            f"context_tail_200={last_200!r}"
        )
        logger.info(llm_debug_log)
        print(llm_debug_log, flush=True)

        stream, target_model = self.llm_router.generate_stream(
            messages=messages,
            model_name=target_model,
            groq_api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p
        )

        return stream, context_block, target_model, active_mapping
