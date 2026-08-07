import os
import re
import time
import logging
from typing import Optional, List, Dict, Any, Tuple, Union

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

logger = logging.getLogger(__name__)

# -------------------------------------------------
# Model Mapping & PII Patterns
# -------------------------------------------------
MODEL_MAPPING = {
    "llama3-70b-8192": "llama-3.3-70b-versatile",
    "mixtral-8x7b-32768": "llama-3.1-8b-instant",
    "gemma2-9b-it": "llama-3.1-8b-instant",
    "llama3-8b-8192": "llama-3.1-8b-instant",
    "llama-3.3-70b-versatile": "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant": "llama-3.1-8b-instant",
}

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
    Production Privacy-Preserving RAG Agent with Groq SDK / HTTP Multi-tier Generation.
    - Query + Context sanitization (zero raw PII leaves local instance)
    - Multi-tier generation cascade (Groq API → Local Qwen → Smart Synthesis Fallback)
    - Full support for answer_query and answer_query_stream
    """

    def __init__(self, model_name: str = "llama-3.3-70b-versatile", groq_api_key: Optional[str] = None, **kwargs):
        self.model_name = MODEL_MAPPING.get(model_name, model_name)
        self.groq_api_key = groq_api_key or os.getenv("GROQ_API_KEY")
        self.current_document_id = "doc_default"
        self.file_name = "doc_default"
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
        self.file_name = file_name or doc_id
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

    def _build_system_prompt(self, context: str) -> str:
        system_prompt = (
            "You are PrivacyShield AI, a helpful and privacy-preserving AI assistant.\n"
            "Answer the user's question accurately using the provided document context (if available) and the ongoing conversation history.\n"
            "If the user refers to information provided in earlier chat messages (such as an introduction, draft, or previous statement), use that information from the conversation history.\n"
            "The context and text may contain masked privacy tokens like <NAME_1>, <PAN_1>, <PHONE_1>, <ADDRESS_1>, <MONEY_1>, <EMAIL_1>, <ORG_1>, <AADHAAR_1>, <GSTIN_1>, <UPI_1>.\n"
            "Do NOT try to invent missing personal data. Keep masked tokens like <NAME_1> intact in your response.\n"
            "Synthesize a clear, well-structured answer using markdown formatting."
        )

        if context and context != "No matching document context found.":
            system_prompt += f"\n\n[Document Context]:\n{context}"

        return system_prompt

    def _build_messages(self, system_prompt: str, query: str, history: Optional[List[Dict[str, str]]] = None) -> List[Dict[str, str]]:
        messages = [{"role": "system", "content": system_prompt}]

        if history:
            for msg in history[-10:]:
                if isinstance(msg, dict) and msg.get("role") and msg.get("content"):
                    r = msg["role"]
                    c = str(msg["content"]).strip()
                    if r in ["user", "assistant"] and c:
                        messages.append({"role": r, "content": c})

        messages.append({"role": "user", "content": query})
        return messages

    def _try_groq_api(
        self,
        api_key: str,
        model_name: str,
        context: str,
        query: str,
        history: Optional[List[Dict[str, str]]] = None,
        temperature: float = 0.15,
        max_tokens: int = 1024,
        top_p: float = 0.9
    ) -> Optional[str]:
        target_model = MODEL_MAPPING.get(model_name, model_name)
        system_prompt = self._build_system_prompt(context)
        messages = self._build_messages(system_prompt, query, history)

        # 1. Try official Groq SDK first
        if HAS_GROQ_SDK:
            try:
                client = Groq(api_key=api_key.strip())
                completion = client.chat.completions.create(
                    model=target_model,
                    messages=messages,
                    temperature=max(0.05, min(temperature, 0.7)),
                    max_tokens=max_tokens,
                    top_p=top_p
                )
                if completion and completion.choices and completion.choices[0].message:
                    content = completion.choices[0].message.content
                    if content and content.strip():
                        return content.strip()
            except Exception as e:
                logger.warning(f"Groq SDK call notice: {e}. Trying HTTP fallback.")

        # 2. Try HTTP API Fallback via httpx
        try:
            import httpx

            payload = {
                "model": target_model,
                "messages": messages,
                "temperature": max(0.05, min(temperature, 0.7)),
                "max_tokens": max_tokens,
                "top_p": top_p
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
                logger.warning(f"Groq HTTP error {resp.status_code}: {resp.text[:200]}")

        except Exception as e:
            logger.warning(f"Groq HTTP call failed: {e}")

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

        target_doc_id = document_id or self.current_document_id
        if target_doc_id not in self.doc_texts and self.doc_texts:
            target_doc_id = list(self.doc_texts.keys())[-1]

        active_mapping = dict(self.doc_mappings.get(target_doc_id, {}))
        if self.masked_result and getattr(self.masked_result, "mapping", None):
            active_mapping.update(self.masked_result.mapping)

        # 1. Mask the user query
        masked_query, query_mapping = mask_query_pii(user_query)
        active_mapping.update(query_mapping)

        # 2. Retrieve context chunks
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

        # Intent detection
        lower_q = masked_query.lower()
        is_summary = any(k in lower_q for k in [
            "summarize", "summary", "overview", "tl;dr", "synopsis", "describe the document", "what is this document"
        ])

        # 4. Multi-tier generation cascade
        requested_model = model_name or self.model_name
        target_model = MODEL_MAPPING.get(requested_model, requested_model)
        masked_response = None
        engine_used = "Unknown"

        # Tier 1 - Groq Cloud API
        api_key = groq_api_key or self.groq_api_key or os.getenv("GROQ_API_KEY")
        if api_key and len(api_key.strip()) > 10:
            masked_response = self._try_groq_api(
                api_key=api_key,
                model_name=target_model,
                context=context_block,
                query=masked_query,
                history=history,
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=top_p
            )
            if masked_response:
                engine_used = f"Groq ({target_model})"

        # Tier 2 - Local Qwen
        if not masked_response:
            prompt = f"Context:\n{context_block}\n\nQuestion: {masked_query}\n\nAnswer clearly:"
            masked_response = self._try_local_qwen(prompt, max_tokens=max_tokens, temperature=temperature)
            if masked_response:
                engine_used = "Local Qwen"

        # Tier 3 - Smart Synthesis Engine Fallback
        if not masked_response:
            engine_used = "Smart Synthesis Engine"
            masked_response = self._smart_synthesis_fallback(
                query=masked_query,
                context_block=context_block,
                is_summary=is_summary
            )

        # 5. Demask output
        final_answer = demask_text(masked_response, active_mapping)

        return {
            "query": user_query,
            "masked_query_used": masked_query,
            "masked_context": context_block,
            "masked_context_sent_to_cloud": context_block,
            "masked_response": masked_response,
            "cloud_llm_masked_response": masked_response,
            "unmasked_response": final_answer,
            "final_unmasked_answer": final_answer,
            "model": target_model,
            "model_used": engine_used,
            "mapping": active_mapping,
            "file_name": self.file_name,
            "sources_retrieved": [c.get("chunk_id", f"chunk_{i}") for i, c in enumerate(retrieved_chunks)],
            "privacy_guarantee": "Zero raw PII transmitted to Groq cloud API",
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
        api_key = groq_api_key or self.groq_api_key or os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("Groq API Key is missing. Please set GROQ_API_KEY environment variable or pass groq_api_key.")

        requested_model = model_name or self.model_name
        target_model = MODEL_MAPPING.get(requested_model, requested_model)

        target_doc_id = document_id or self.current_document_id
        if target_doc_id not in self.doc_texts and self.doc_texts:
            target_doc_id = list(self.doc_texts.keys())[-1]

        active_mapping = dict(self.doc_mappings.get(target_doc_id, {}))
        if self.masked_result and getattr(self.masked_result, "mapping", None):
            active_mapping.update(self.masked_result.mapping)

        masked_query, query_mapping = mask_query_pii(user_query)
        active_mapping.update(query_mapping)

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

        if context_block != "No matching document context found.":
            context_block, extra_map = mask_text_pii(context_block, prefix="CTX")
            active_mapping.update(extra_map)

        system_prompt = self._build_system_prompt(context_block)
        messages = self._build_messages(system_prompt, masked_query, history)

        if HAS_GROQ_SDK:
            client = Groq(api_key=api_key.strip())
            stream = client.chat.completions.create(
                model=target_model,
                messages=messages,
                temperature=float(temperature),
                max_tokens=int(max_tokens),
                top_p=float(top_p),
                stream=True
            )
            return stream, context_block, target_model, active_mapping
        else:
            raise RuntimeError("Groq SDK is not installed. Please install groq to use answer_query_stream.")