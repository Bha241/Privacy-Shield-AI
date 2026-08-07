import spacy
import spacy.cli
import re
import logging
from pii_detector.schemas.entities import Entity

logger = logging.getLogger(__name__)


class SpacyRecognizer:
    """Lightweight CPU-optimized NER recognizer using spaCy."""

    def __init__(self, model_name: str = "en_core_web_sm"):
        self.model_name = model_name
        self._nlp = None
        # Mapping spaCy labels to standard PII entity labels
        self.label_map = {
            "PERSON": "NAME",
            "ORG": "ORGANIZATION",
            "GPE": "LOCATION",
            "LOC": "LOCATION",
            "FAC": "LOCATION",
            "MONEY": "MONEY",
        }

    @property
    def nlp(self):
        if self._nlp is None:
            try:
                self._nlp = spacy.load(self.model_name)
            except Exception as e:
                logger.warning(f"spaCy model {self.model_name} not available, using blank 'en' model: {e}")
                self._nlp = spacy.blank("en")
        return self._nlp

    def _is_valid_entity(self, text: str, label: str) -> bool:
        clean = text.strip()
        if len(clean) < 2:
            return False
        # Filter out purely numeric or punctuation strings from NAME / ORG / LOCATION
        if label in {"NAME", "ORGANIZATION", "LOCATION"}:
            if re.match(r"^[\d\s\-_.,/()]+$", clean):
                return False
            # Filter out common false positive keywords and label headers
            noise_words = {
                "dob", "name", "customer name", "address", "phone", "email",
                "pan", "aadhaar", "dl", "uid", "mobile", "account number",
                "upi id", "attached scanned id card below", "ticket",
                "taxpan", "taxpan id", "tax id", "direct mobile", "contact email",
                "primary representative", "document reference"
            }
            if clean.lower() in noise_words:
                return False
        return True

    def _clean_entity_text(self, text: str, start: int, end: int):
        words = text.split()
        stop_words = {"has", "visited", "is", "was", "are", "were", "and", "with", "for", "at", "in", "to", "from", "of", "by", "on", "the", "a", "an", "or", "had", "been", "via"}
        while len(words) > 1 and words[-1].lower() in stop_words:
            words.pop()
        trimmed_text = " ".join(words)
        trimmed_end = start + len(trimmed_text)
        return trimmed_text, start, trimmed_end

    def recognize(self, text: str):
        doc = self.nlp(text)
        entities = []
        for ent in doc.ents:
            if ent.label_ in self.label_map:
                pii_label = self.label_map[ent.label_]
                if self._is_valid_entity(ent.text, pii_label):
                    c_text, c_start, c_end = self._clean_entity_text(ent.text, ent.start_char, ent.end_char)
                    if len(c_text) >= 2:
                        entities.append(
                            Entity(
                                text=c_text,
                                label=pii_label,
                                start=c_start,
                                end=c_end,
                                confidence=0.90,
                                source="spacy",
                            )
                        )
        return entities
