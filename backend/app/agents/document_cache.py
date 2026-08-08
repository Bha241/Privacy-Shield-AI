"""
PrivacyShieldAI - Document Cache Module
Stores and manages full document structures, page maps, section maps,
and PII mappings in memory for instant document-level context assembly without vector retrieval.
"""

import time
import re
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional


@dataclass
class CachedDocument:
    document_id: str
    file_name: str
    masked_text: str
    mapping: Dict[str, str] = field(default_factory=dict)
    page_map: Dict[str, str] = field(default_factory=dict)
    section_map: Dict[str, str] = field(default_factory=dict)
    ingested_at: float = field(default_factory=time.time)
    character_count: int = 0
    word_count: int = 0


class DocumentCache:
    """
    High-performance in-memory cache for full document representations.
    Allows instant access to full document text for document-level queries (summaries, overviews, analysis).
    """

    def __init__(self):
        self._cache: Dict[str, CachedDocument] = {}
        self._latest_doc_id: Optional[str] = None

    def store(
        self,
        document_id: str,
        masked_text: str,
        mapping: Optional[Dict[str, str]] = None,
        file_name: Optional[str] = None,
        page_map: Optional[Dict[str, str]] = None,
        section_map: Optional[Dict[str, str]] = None
    ) -> CachedDocument:
        """Stores a sanitized document structure in the cache."""
        cleaned_text = (masked_text or "").strip()
        words = len(re.findall(r"\w+", cleaned_text))

        doc = CachedDocument(
            document_id=document_id,
            file_name=file_name or document_id,
            masked_text=cleaned_text,
            mapping=dict(mapping or {}),
            page_map=dict(page_map or {}),
            section_map=dict(section_map or {}),
            ingested_at=time.time(),
            character_count=len(cleaned_text),
            word_count=words
        )

        self._cache[document_id] = doc
        if file_name:
            self._cache[file_name] = doc
        self._latest_doc_id = document_id
        return doc

    def get(self, document_id: Optional[str] = None) -> Optional[CachedDocument]:
        """Retrieves a cached document by ID or filename, falling back to the latest ingested document."""
        if document_id and document_id in self._cache:
            return self._cache[document_id]
        if document_id:
            for doc in self._cache.values():
                if doc.file_name == document_id:
                    return doc
        if self._latest_doc_id and self._latest_doc_id in self._cache:
            return self._cache[self._latest_doc_id]
        if self._cache:
            latest_id = list(self._cache.keys())[-1]
            return self._cache[latest_id]
        return None

    def get_full_text(self, document_id: Optional[str] = None) -> str:
        """Returns the full masked text of a document."""
        doc = self.get(document_id)
        return doc.masked_text if doc else ""

    def get_mapping(self, document_id: Optional[str] = None) -> Dict[str, str]:
        """Returns the PII token mapping dictionary for a document."""
        doc = self.get(document_id)
        return dict(doc.mapping) if doc else {}

    def get_latest_doc_id(self) -> Optional[str]:
        """Returns the ID of the most recently ingested document."""
        return self._latest_doc_id

    def has_document(self, document_id: Optional[str] = None) -> bool:
        """Checks if a document exists in cache."""
        if document_id:
            if document_id in self._cache:
                return True
            for doc in self._cache.values():
                if doc.file_name == document_id:
                    return True
            return False
        return bool(self._cache)


# Global Singleton Document Cache Instance
document_cache = DocumentCache()
