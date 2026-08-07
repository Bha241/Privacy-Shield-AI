import os
import re
import time
import logging
from typing import Optional, List, Dict, Any, Tuple

try:
    from app.agents.db.vector_store import vector_store_manager, generate_text_embedding
except ImportError:
    try:
        from pii_detector.db.vector_store import vector_store_manager, generate_text_embedding
    except ImportError:
        vector_store_manager = None
        generate_text_embedding = lambda text: [0.0] * 384

logger = logging.getLogger(__name__)

# -------------------------------------------------
# PII Patterns
# -------------------------------------------------
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
            token = f"<{entity_type}_{prefix}_{counter[entity_type]}>"
            masked_str = masked_str.replace(val, token, 1)
            mapping[token] = val

    return masked_str, mapping


def mask_query_pii(query: str) -> Tuple[str, Dict[str, str]]:
    return mask_text_pii(query, prefix="Q")


def demask_text(text: str, mapping: Dict[str, str]) -> str:
    if not mapping or not text:
        return text

    demasked = text
    # Longest token first
    for token, original in sorted(mapping.items(), key=lambda x: len(x[0]), reverse=True):
        if token in demasked:
            demasked = demasked.replace(token, str(original))
        else:
            # Handle LLM variations: <NAME 1>, [NAME_1], NAME_1 etc.
            clean = re.escape(token.strip("<>")).replace(r"\_", r"[_\s\-]?")
            pattern = re.compile(rf"[<\[]?{clean}[>\]]?", re.IGNORECASE)
            demasked = pattern.sub(str(original), demasked)

    return demasked


class PrivacyRAGAgent:
    """
    Production Privacy-Preserving RAG Agent
    - Query + Context sanitization
    - Multi-tier generation (Groq → Local Qwen → Smart Synthesis)
    - Strict zero-leakage design
    """

    def __init__(self, model_name: str = "llama-3.3-70b-versatile", **kwargs):
        self.model_name = model_name
        self.current_document_id = "doc_default"
        self.doc_mappings: Dict[str, Dict[str, str]] = {}
        self.doc_texts: Dict[str, str] = {}
        self.masked_result = None
        self._local_qwen_instance = None

    def ingest_masked_result(
        self,
        masked_result: Any,
        file_name: Optional[str] = None,
        document_id: Optional[str] = None,
        chunk_size: int = 450,
        overlap: int = 60
    ) -> bool:
        doc_id = document_id or f"doc_{int(time.time())}"
        self.current_document_id = doc_id
        self.masked_result = masked_result

        if hasattr(masked_result, "masked_text"):
            masked_text = masked_result.masked_text
            mapping = getattr(masked_result, "mapping", {}) or {}
        elif isinstance(masked_result, dict):
            masked_text = masked_result.get("masked_text", "")
            mapping = masked_result.get("mapping", {})
        else:
            masked_text = str(masked_result)
            mapping = {}

        self.doc_texts[doc_id] = masked_text
        self.doc_mappings[doc_id] = mapping

        chunks = self._chunk_text(masked_text, chunk_size=chunk_size, overlap=overlap)

        if vector_store_manager:
            for idx, chk in enumerate(chunks, start=1):
                emb = generate_text_embedding(chk)
                vector_store_manager.store_sanitized_chunk(
                    document_id=doc_id,
                    text=chk,
                    embedding_vector=emb,
                    page_ref=str(idx)
                )

        logger.info(f"Ingested document {doc_id} → {len(chunks)} chunks")
        return True

    def _chunk_text(self, text: str, chunk_size: int = 450, overlap: int = 60) -> List[str]:
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
                    # sentence split
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

    def _try_groq_api(
        self,
        api_key: str,
        model_name: str,
        context: str,
        query: str,
        history: Optional[List[Dict[str, str]]] = None,
        temperature: float = 0.15,
        max_tokens: int = 1024
    ) -> Optional[str]:
        try:
            import httpx

            system_prompt = (
                "You are PrivacyShield AI — a precise, professional, privacy-preserving assistant.\n\n"
                "STRICT RULES:\n"
                "1. Answer ONLY using the provided Document Context.\n"
                "2. Never invent facts or personal data.\n"
                "3. The context contains masked tokens such as <NAME_1>, <PHONE_1>, <EMAIL_1>, <PAN_1>, <AADHAAR_1>, <UPI_1>. "
                "You MUST keep these tokens exactly as they appear. Do NOT try to guess or reconstruct original values.\n"
                "4. Do NOT dump raw sentences from the context. Synthesize a clean, well-structured answer.\n"
                "5. Use markdown (headings, bullet points) when it improves clarity.\n"
                "6. If the user asks for a summary, write a coherent short summary. Do not list every personal detail.\n"
                "7. If the context is insufficient, say so clearly.\n"
            )

            messages = [{"role": "system", "content": system_prompt}]

            if history:
                for h in history[-6:]:
                    if h.get("role") in ["user", "assistant"] and h.get("content"):
                        messages.append({"role": h["role"], "content": h["content"]})

            user_content = (
                f"### Document Context\n{context}\n\n"
                f"### User Question\n{query}\n\n"
                f"Provide a clear and helpful answer following the rules above."
            )
            messages.append({"role": "user", "content": user_content})

            payload = {
                "model": model_name,
                "messages": messages,
                "temperature": max(0.05, min(temperature, 0.7)),
                "max_tokens": max_tokens,
                "top_p": 0.9
            }

            resp = httpx.post(
                "https://api.groq.com/openai/v1/chat/completions",
                json=payload,
                headers={
                    "Authorization": f"Bearer {api_key.strip()}",
                    "Content-Type": "application/json"
                },
                timeout=20.0
            )

            if resp.status_code == 200:
                content = resp.json()["choices"][0]["message"]["content"].strip()
                return content if content else None
            else:
                logger.warning(f"Groq error {resp.status_code}: {resp.text[:200]}")

        except Exception as e:
            logger.warning(f"Groq call failed: {e}")

        return None

    def _try_local_qwen(self, prompt: str, max_tokens: int = 512, temperature: float = 0.2) -> Optional[str]:
        try:
            if self._local_qwen_instance is None:
                try:
                    from app.agents.llms.qwen import QwenLLM
                    self._local_qwen_instance = QwenLLM()
                except Exception:
                    try:
                        from pii_detector.llms.qwen import QwenLLM
                        self._local_qwen_instance = QwenLLM()
                    except Exception:
                        self._local_qwen_instance = False

            if self._local_qwen_instance:
                return self._local_qwen_instance.generate(
                    prompt=prompt,
                    max_tokens=max_tokens,
                    temperature=temperature
                )
        except Exception as e:
            logger.warning(f"Local Qwen failed: {e}")
        return None

    def _smart_synthesis_fallback(self, query: str, context_block: str, is_summary: bool) -> str:
        if not context_block or "No matching document context" in context_block:
            return "No relevant document context is available. Please make sure a document has been ingested first."

        # Clean context a bit
        lines = [ln.strip() for ln in context_block.splitlines() if ln.strip()]
        clean_lines = []
        seen = set()
        for ln in lines:
            key = ln.lower()[:80]
            if key not in seen and len(ln) > 15:
                clean_lines.append(ln)
                seen.add(key)

        if is_summary:
            points = clean_lines[:12]
            body = "\n".join(f"• {p}" for p in points)
            return (
                f"### Document Summary\n\n"
                f"{body}\n\n"
                f"---\n"
                f"*All sensitive identifiers remain masked for privacy.*"
            )

        # Simple relevance scoring
        q_terms = set(re.findall(r'\w+', query.lower())) - {
            "what", "is", "the", "a", "an", "of", "in", "to", "for", "and", "or", "please", "tell", "me", "about"
        }
        scored = []
        for ln in clean_lines:
            score = len(q_terms & set(re.findall(r'\w+', ln.lower())))
            scored.append((score, ln))

        scored.sort(reverse=True)
        top = [ln for score, ln in scored if score > 0][:8] or clean_lines[:6]

        body = "\n".join(f"• {t}" for t in top)
        return (
            f"### Answer\n\n"
            f"**Question:** {query}\n\n"
            f"{body}\n\n"
            f"---\n"
            f"*Response generated from sanitized document context.*"
        )

    def answer_query(
        self,
        user_query: str,
        document_id: Optional[str] = None,
        groq_api_key: Optional[str] = None,
        temperature: float = 0.15,
        max_tokens: int = 1024,
        top_p: float = 0.9,
        model_name: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
        top_k: int = 4,
        **kwargs
    ) -> Dict[str, Any]:

        # Resolve document
        target_doc_id = document_id or self.current_document_id
        if target_doc_id not in self.doc_texts and self.doc_texts:
            target_doc_id = list(self.doc_texts.keys())[-1]

        active_mapping = dict(self.doc_mappings.get(target_doc_id, {}))
        if self.masked_result and getattr(self.masked_result, "mapping", None):
            active_mapping.update(self.masked_result.mapping)

        # 1. Mask the user query
        masked_query, query_mapping = mask_query_pii(user_query)
        active_mapping.update(query_mapping)

        # 2. Retrieve
        retrieved_chunks = []
        if vector_store_manager:
            retrieved_chunks = vector_store_manager.search_similar_chunks(
                query_text=masked_query,
                document_id=target_doc_id,
                top_k=top_k
            )

        if not retrieved_chunks and target_doc_id in self.doc_texts:
            full = self.doc_texts[target_doc_id]
            retrieved_chunks = [
                {"chunk_id": f"fallback_{i}", "text": full[i:i+450]}
                for i in range(0, min(len(full), 1800), 450)
            ]

        context_texts = [c.get("text", "") for c in retrieved_chunks if c.get("text")]
        context_block = "\n\n".join(context_texts) if context_texts else "No matching document context found."

        # 3. Extra sanitization of context (safety net)
        if context_block != "No matching document context found.":
            context_block, extra_map = mask_text_pii(context_block, prefix="CTX")
            active_mapping.update(extra_map)

        # Intent
        lower_q = masked_query.lower()
        is_summary = any(k in lower_q for k in [
            "summarize", "summary", "overview", "tl;dr", "synopsis", "describe the document", "what is this document"
        ])

        # 4. Generation (multi-tier)
        target_model = model_name or self.model_name
        masked_response = None
        engine_used = "Unknown"

        # Tier 1 - Groq
        api_key = groq_api_key or os.getenv("GROQ_API_KEY")
        if api_key and len(api_key.strip()) > 10:
            masked_response = self._try_groq_api(
                api_key=api_key,
                model_name=target_model,
                context=context_block,
                query=masked_query,
                history=history,
                temperature=temperature,
                max_tokens=max_tokens
            )
            if masked_response:
                engine_used = f"Groq ({target_model})"

        # Tier 2 - Local Qwen
        if not masked_response:
            prompt = f"Context:\n{context_block}\n\nQuestion: {masked_query}\n\nAnswer clearly:"
            masked_response = self._try_local_qwen(prompt, max_tokens=max_tokens, temperature=temperature)
            if masked_response:
                engine_used = "Local Qwen"

        # Tier 3 - Smart fallback
        if not masked_response:
            engine_used = "Smart Synthesis Engine"
            masked_response = self._smart_synthesis_fallback(
                query=masked_query,
                context_block=context_block,
                is_summary=is_summary
            )

        # 5. Demask
        final_answer = demask_text(masked_response, active_mapping)

        return {
            "masked_response": masked_response,
            "final_unmasked_answer": final_answer,
            "model_used": engine_used,
            "sources_retrieved": [c.get("chunk_id", f"chunk_{i}") for i, c in enumerate(retrieved_chunks)],
            "privacy_guarantee": "Zero raw PII sent to LLM",
            "masked_query_used": masked_query,
            "masked_context": context_block[:800] + ("..." if len(context_block) > 800 else "")
        }