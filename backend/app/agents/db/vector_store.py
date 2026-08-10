import json
import logging
import hashlib
import re
from typing import List, Dict, Any, Optional
import numpy as np

try:
    from app.agents.db.models import SanitizedChunkModel
except ImportError:
    try:
        from pii_detector.db.models import SanitizedChunkModel
    except ImportError:
        SanitizedChunkModel = None

logger = logging.getLogger(__name__)


def generate_text_embedding(text: str, dim: int = 384) -> List[float]:
    """
    Generates a deterministic, normalized 384-dimensional dense embedding vector 
    using character & subword n-gram hashing. Works offline with zero dependencies.
    """
    if not text:
        return [0.0] * dim

    vec = np.zeros(dim, dtype=np.float32)
    words = text.lower().split()
    
    # 1. Word level hashing
    for word in words:
        h = int(hashlib.md5(word.encode('utf-8')).hexdigest(), 16)
        idx = h % dim
        val = ((h >> 16) % 1000) / 1000.0
        vec[idx] += val

    # 2. Subword 3-gram hashing
    clean_text = text.lower()
    for i in range(len(clean_text) - 2):
        ngram = clean_text[i:i+3]
        h = int(hashlib.sha256(ngram.encode('utf-8')).hexdigest()[:8], 16)
        idx = h % dim
        vec[idx] += 0.5

    # Normalize vector to unit length
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm

    return vec.tolist()


class VectorStoreManager:
    """
    Vector DB Index Manager for Sanitized Chunks (pgvector / FAISS / Cosine Similarity Index).
    Persists embedding vectors and performs semantic vector similarity searches over sanitized document chunks.
    """

    def __init__(self):
        self.chunks_cache: List[Dict[str, Any]] = []

    def store_sanitized_chunk(
        self,
        db_session=None,
        document_id: str = "doc_default",
        document_name: Optional[str] = None,
        text: str = "",
        embedding_vector: Optional[List[float]] = None,
        page_ref: str = "1",
        chunk_index: int = 1
    ) -> Optional[Any]:
        """Persists sanitized chunk entity and embedding vector."""
        if not embedding_vector:
            embedding_vector = generate_text_embedding(text)

        chunk_id = f"chk_{hashlib.md5((document_id + text[:30]).encode()).hexdigest()[:12]}"
        
        chunk_obj = None
        if db_session and SanitizedChunkModel:
            try:
                chunk_obj = SanitizedChunkModel(
                    chunk_id=chunk_id,
                    document_id=document_id,
                    text=text,
                    page_ref=page_ref,
                    chunk_index=chunk_index
                )
                chunk_obj.set_vector(embedding_vector)
                db_session.add(chunk_obj)
                db_session.commit()
                db_session.refresh(chunk_obj)
            except Exception as err:
                logger.warning(f"Failed to persist chunk to DB: {err}")
                if db_session:
                    db_session.rollback()

        # Update local memory cache
        cache_item = {
            "chunk_id": chunk_id,
            "document_id": document_id,
            "document_name": document_name or document_id,
            "text": text,
            "vector": np.array(embedding_vector, dtype=np.float32),
            "page_ref": page_ref,
            "chunk_index": chunk_index
        }
        # Avoid duplicate chunk cache entries
        self.chunks_cache = [c for c in self.chunks_cache if c["chunk_id"] != chunk_id]
        self.chunks_cache.append(cache_item)

        return chunk_obj or cache_item

    def hydrate_document(self, document_id: str) -> int:
        """Load only one document's sanitized chunks from persistent storage."""
        if not document_id:
            return 0
        try:
            from app.agents.db.database import db_manager
            with db_manager.get_session() as session:
                rows = session.query(SanitizedChunkModel).filter(
                    SanitizedChunkModel.document_id == document_id
                ).all()
                document_name = document_id
                try:
                    from pii_detector.db.models import DocumentModel
                    document = session.get(DocumentModel, document_id)
                    document_name = document.filename if document else document_id
                except Exception:
                    pass
                for row in rows:
                    vector = row.get_vector()
                    item = {
                        "chunk_id": row.chunk_id,
                        "document_id": row.document_id,
                        "document_name": document_name,
                        "text": row.text,
                        "vector": np.array(vector, dtype=np.float32),
                        "page_ref": row.page_ref or "1",
                        "chunk_index": row.chunk_index or 1,
                    }
                    self.chunks_cache = [
                        c for c in self.chunks_cache if c["chunk_id"] != row.chunk_id
                    ]
                    self.chunks_cache.append(item)
                return len(rows)
        except Exception as err:
            logger.debug("Document chunk hydration skipped: %s", err)
            return 0

    def remove_documents(self, document_ids: set[str]) -> None:
        """Remove expired document chunks from the in-memory vector index."""
        self.chunks_cache = [
            chunk for chunk in self.chunks_cache
            if chunk.get("document_id") not in document_ids
        ]

    def search_similar_chunks(
        self,
        query_vector: Optional[List[float]] = None,
        query_text: Optional[str] = None,
        document_id: Optional[str] = None,
        top_k: int = 4,
        db_session=None
    ) -> List[Dict[str, Any]]:
        """
        Executes Cosine Similarity / pgvector Search against stored sanitized chunks.
        """
        if not query_vector and query_text:
            query_vector = generate_text_embedding(query_text)

        if not query_vector:
            return []

        # Retrieval without an explicit document scope is forbidden. The chat
        # API validates this earlier, and this guard protects other callers.
        if not document_id:
            return []

        # 1. Check PostgreSQL pgvector if db_session is provided
        if db_session and SanitizedChunkModel:
            try:
                # Only run sync DB query if session is not async
                from sqlalchemy.ext.asyncio import AsyncSession
                if not isinstance(db_session, AsyncSession):
                    from sqlalchemy import text as sa_text
                    query_vec_str = f"[{','.join(str(x) for x in query_vector)}]"
                    sql = sa_text("""
                        SELECT chunk_id, document_id, text, page_ref
                        FROM sanitized_chunks
                        WHERE document_id = :doc_id
                        ORDER BY embedding_vector <-> :vec
                        LIMIT :k
                    """)
                    res = db_session.execute(sql, {"doc_id": document_id, "vec": query_vec_str, "k": top_k}).fetchall()

                    if res:
                        return [
                            {
                                "chunk_id": r[0],
                                "document_id": r[1],
                                "text": r[2],
                                "page_ref": r[3],
                                "score": 0.95
                            }
                            for r in res
                        ]
            except Exception as err:
                logger.debug(f"DB vector query bypassed: {err}")

        # 2. NumPy Cosine Similarity & Keyword Overlap Search over cached chunks
        q_vec = np.array(query_vector, dtype=np.float32)
        norm_q = np.linalg.norm(q_vec)

        # STRICT DOCUMENT ISOLATION: If document_id is provided, search ONLY chunks for that document_id
        if document_id:
            candidates = [c for c in self.chunks_cache if c.get("document_id") == document_id]
            if not candidates:
                self.hydrate_document(document_id)
                candidates = [c for c in self.chunks_cache if c.get("document_id") == document_id]
        else:
            candidates = []

        if not candidates:
            return []

        # Prepare tokens for keyword overlap scoring
        query_words = set(re.findall(r'\w+', (query_text or "").lower())) if query_text else set()

        scored_chunks = []
        for item in candidates:
            chunk_text = item.get("text", "")
            chunk_words = set(re.findall(r'\w+', chunk_text.lower()))
            
            # Vector similarity
            vec = item.get("vector")
            similarity = 0.0
            if vec is not None and norm_q > 0:
                norm_v = np.linalg.norm(vec)
                if norm_v > 0 and len(vec) == len(q_vec):
                    similarity = float(np.dot(q_vec, vec) / (norm_q * norm_v))

            # Keyword overlap score (Jaccard / BM25 token hit)
            keyword_score = 0.0
            if query_words and chunk_words:
                common_words = query_words.intersection(chunk_words)
                # Ignore very short common words like 'a', 'in', 'is', 'the'
                meaningful_common = {w for w in common_words if len(w) > 2}
                keyword_score = len(meaningful_common) / max(len(query_words), 1)

            # Combined hybrid score (70% vector + 30% keyword overlap)
            final_score = round((0.7 * similarity) + (0.3 * keyword_score), 4)

            scored_chunks.append({
                "chunk_id": item["chunk_id"],
                "document_id": item["document_id"],
                "document_name": item.get("document_name", item["document_id"]),
                "text": chunk_text,
                "page_ref": item.get("page_ref", "1"),
                "score": final_score
            })

        scored_chunks.sort(key=lambda x: x["score"], reverse=True)
        return scored_chunks[:top_k]



# Global Vector Store Instance
vector_store_manager = VectorStoreManager()
