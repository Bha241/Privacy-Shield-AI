from typing import List, Dict, Any, Optional
from dataclasses import asdict

from pii_detector.recognizers.main_detector import PIIDetector
from pii_detector.readers.document_reader import DocumentReader
from pii_detector.schemas.entities import Entity


class PIIDetectionAgent:
    """
    1. PII Detection Agent:
    Scans input text/documents locally using multi-engine pattern matching,
    NER models, and OCR to identify PII candidates on the go.
    Outputs entity candidates for Human-in-the-loop (HITL) verification.
    """

    def __init__(self, enable_ocr: bool = True, enable_llm_residual: Optional[bool] = None):
        if enable_llm_residual is None:
            from pii_detector.config import MODEL_PATH
            enable_llm_residual = MODEL_PATH.exists()

        self.reader = DocumentReader(enable_ocr=enable_ocr)
        self.detector = PIIDetector(enable_llm=enable_llm_residual)


    def process_file_on_the_go(self, file_path: str, domain: Optional[str] = None) -> Dict[str, Any]:
        """
        Reads document and detects PII candidate entities on the go.
        Returns raw text and structured candidate entities for HITL approval.
        """
        raw_text = self.reader.read_document(file_path)
        if not raw_text.strip():
            return {
                "status": "empty",
                "raw_text": "",
                "detected_entities": [],
                "total_count": 0
            }

        detection_res = self.detector.detect(raw_text, domain=domain)

        entities_list = []
        for idx, e in enumerate(detection_res.all_entities, start=1):
            item = asdict(e)
            item["id"] = idx
            item["approved"] = False  # Candidate status for HITL review - explicit approval required
            item["user_custom_label"] = None
            entities_list.append(item)

        return {
            "status": "success",
            "raw_text": raw_text,
            "domain": domain or "general",
            "detected_entities": entities_list,
            "total_count": len(entities_list),
            "regex_spacy_count": len(detection_res.regex_entities),
            "llm_count": len(detection_res.llm_entities)
        }

    def process_text_on_the_go(self, text: str, domain: Optional[str] = None) -> Dict[str, Any]:
        """Detects PII candidate entities directly from raw text input."""
        detection_res = self.detector.detect(text, domain=domain)

        entities_list = []
        for idx, e in enumerate(detection_res.all_entities, start=1):
            item = asdict(e)
            item["id"] = idx
            item["approved"] = False  # Candidate status for HITL review - explicit approval required
            item["user_custom_label"] = None
            entities_list.append(item)

        return {
            "status": "success",
            "raw_text": text,
            "domain": domain or "general",
            "detected_entities": entities_list,
            "total_count": len(entities_list),
        }
