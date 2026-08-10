from pii_detector.recognizers.regex_recognizer import RegexRecognizer
from pii_detector.recognizers.spacy_recognizer import SpacyRecognizer
from pii_detector.recognizers.credential_recognizer import CredentialRecognizer
from pii_detector.recognizers.structured_recognizer import StructuredRecognizer
from pii_detector.recognizers.presidio_recognizer import PresidioRecognizer
from pii_detector.schemas.detection_results import DetectionResult
from pii_detector.schemas.entities import Entity
import re


class PIIDetector:

    def __init__(self, enable_llm: bool = False):

        self.regex = RegexRecognizer()
        self.spacy = SpacyRecognizer()
        self.presidio = PresidioRecognizer()
        self.credentials = CredentialRecognizer()
        self.structured = StructuredRecognizer()
        self.enable_llm = enable_llm
        self._llm = None

    @property
    def llm(self):
        if self._llm is None:
            from pii_detector.recognizers.llm_recognizer import LLMRecognizer
            self._llm = LLMRecognizer()
        return self._llm

    def _deduplicate_entities(self, entities):
        if not entities:
            return []
        # Resolve containment before confidence. A short generic match (for
        # example a postal code classified as PHONE) must not displace a
        # longer, validated ADDRESS or DATE_OF_BIRTH span containing it.
        source_priority = {
            "regex_structured": 0,
            "credential_context": 0,
            "credential_pattern": 0,
            "context_pattern": 0,
            "presidio": 1,
            "regex": 2,
            "spacy": 3,
        }
        sorted_ents = sorted(
            entities,
            key=lambda e: (
                source_priority.get(getattr(e, "source", ""), 4),
                -(e.end - e.start),
                -getattr(e, "confidence", 0.9),
                e.start
            )
        )
        deduped = []

        for e in sorted_ents:
            overlapping = False
            for prev in deduped:
                if max(e.start, prev.start) < min(e.end, prev.end):
                    overlapping = True
                    break
            if not overlapping:
                deduped.append(e)

        # Return final deduplicated entities ordered by start position
        return sorted(deduped, key=lambda e: e.start)

    def _extract_labeled_context_entities(self, text: str, existing_entities):
        """Recover values following generic enterprise field labels.

        These patterns describe field structure, not document names or sample
        values. They supplement the configured recognizers when OCR/layout
        text leaves a labeled value outside the normal NER span.
        """
        existing_spans = [
            (e.start, e.end, getattr(e, "label", ""))
            for e in existing_entities
        ]
        context_entities = []
        patterns = [
            (r"(?:Primary\s+Contact|Contact\s+Person|Attn|Attention|Warehouse\s+Manager|Buyer|Vendor)\s*[:\-]?\s*(?:Mr\.|Mrs\.|Ms\.|Dr\.)?\s*([A-Z][a-zA-Z.'\-]+(?:\s+[A-Z][a-zA-Z.'\-]+)+)", "NAME", 0.92),
            (r"^Name\s*[:\-]\s*(?:Mr\.|Mrs\.|Ms\.|Dr\.)?\s*([A-Z][a-zA-Z.'\-]+(?:\s+[A-Z][a-zA-Z.'\-]+)+)", "NAME", 0.92),
            (r"Account\s+Name\s*[:\-]\s*([A-Za-z0-9.'\-\s]+?(?:Pvt\.?\s*Ltd\.?|Limited|Inc\.?|Corp\.?|Company))", "ORGANIZATION", 0.90),
            (r"Company\s*[:\-]\s*([A-Za-z0-9.'\-\s]+?(?:Pvt\.?\s*Ltd\.?|Limited|Inc\.?|Corp\.?))", "ORGANIZATION", 0.90),
            (r"Account\s+Number\s*[:\-]\s*(\d{9,18})\b", "BANK_ACCOUNT", 0.95),
            (r"MSME\s*[:\-]\s*([A-Za-z0-9\-]+)\b", "MSME", 0.95),
            (r"SWIFT\s*[:\-]\s*([A-Z0-9]{8,11})\b", "SWIFT", 0.95),
        ]
        for pattern, label, confidence in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE):
                if not match.lastindex:
                    continue
                value = match.group(1).strip()
                start, end = match.start(1), match.end(1)
                overlaps = any(
                    label not in {"PHONE", "ACCOUNT_NUMBER", "PINCODE"}
                    and not (end <= old_start or start >= old_end)
                    for old_start, old_end, label in existing_spans
                )
                if value and len(value) >= 3 and not overlaps:
                    context_entities.append(Entity(value, label, start, end, confidence, "context_pattern"))
                    existing_spans.append((start, end, label))
        return context_entities

    def detect(self, text, use_llm_residual: bool = True, domain: str = "general"):
        # PII detection uses the deterministic Fast pipeline. It combines the
        # configured recognizers so credentials, structured identifiers, dates,
        # addresses, and general entities are handled without a separate model
        # mode or shared model state.
        presidio_entities = self.presidio.recognize(text)
        # The supplied Presidio detector is available as an explicit Fast-mode
        # engine through PRIVACYSHIELD_ENABLE_PRESIDIO=true. The stable
        # regex+spaCy path remains the default compatibility engine because
        # Presidio can terminate on incompatible local NLP installations.
        if presidio_entities:
            regex_entities = []
            spacy_entities = []
        else:
            regex_entities = self.regex.recognize(text, domain=domain)
            spacy_entities = self.spacy.recognize(text)
        credential_entities = self.credentials.recognize(text)
        structured_entities = self.structured.recognize(text)

        context_entities = self._extract_labeled_context_entities(
            text,
            presidio_entities + regex_entities + spacy_entities + credential_entities + structured_entities,
        )

        llm_entities = []
        if self.enable_llm:
            combined = presidio_entities + regex_entities + spacy_entities + credential_entities + structured_entities + context_entities
            if use_llm_residual and combined:
                last_end = 0
                sorted_combined = sorted(combined, key=lambda e: e.start)
                residual_parts = []
                for e in sorted_combined:
                    if e.start > last_end:
                        seg = text[last_end:e.start].strip()
                        if len(seg) > 8:
                            residual_parts.append(seg)
                    last_end = max(last_end, e.end)
                if last_end < len(text):
                    seg = text[last_end:].strip()
                    if len(seg) > 8:
                        residual_parts.append(seg)

                residual_text = "\n".join(residual_parts)
                if residual_text.strip():
                    llm_entities = self.llm.recognize(residual_text)
            else:
                llm_entities = self.llm.recognize(text)

        all_raw = presidio_entities + regex_entities + spacy_entities + credential_entities + structured_entities + context_entities + llm_entities
        deduped_entities = self._deduplicate_entities(all_raw)

        return DetectionResult(
            original_text=text,
            regex_entities=presidio_entities + regex_entities + spacy_entities + credential_entities + structured_entities + context_entities,
            llm_entities=llm_entities,
            all_entities=deduped_entities
        )
