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

        # The canonical document ID is the only cache key. Filenames are not
        # unique and must never become aliases for another document's state.
        self._cache[document_id] = doc
        return doc

    def get(self, document_id: Optional[str] = None) -> Optional[CachedDocument]:
        """Retrieves only the explicitly requested canonical document ID."""
        if not document_id:
            return None
        return self._cache.get(document_id)

    def get_full_text(self, document_id: Optional[str] = None) -> str:
        """Returns the full masked text of a document."""
        doc = self.get(document_id)
        return doc.masked_text if doc else ""

    def get_mapping(self, document_id: Optional[str] = None) -> Dict[str, str]:
        """Returns the PII token mapping dictionary for a document."""
        doc = self.get(document_id)
        return dict(doc.mapping) if doc else {}

    def get_latest_doc_id(self) -> Optional[str]:
        """Compatibility helper; callers must not use this as chat context."""
        return None

    def has_document(self, document_id: Optional[str] = None) -> bool:
        """Checks if a document exists in cache."""
        return bool(document_id and document_id in self._cache)

    def remove(self, document_id: str) -> None:
        """Invalidate one document after retention purge."""
        self._cache.pop(document_id, None)

    def remove_many(self, document_ids: set[str]) -> None:
        """Invalidate expired documents without touching other cached documents."""
        for document_id in document_ids:
            self.remove(document_id)


# Global Singleton Document Cache Instance
document_cache = DocumentCache()
