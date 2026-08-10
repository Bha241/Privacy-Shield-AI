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

    def _is_valid_entity(self, text: str, label: str, source_text: str = "", start: int = 0, end: int = 0) -> bool:
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
                "date of birth", "birth date", "birth", "mailing address",
                "permanent address", "residential address", "home address",
                "pan", "aadhaar", "dl", "uid", "mobile", "account number",
                "upi id", "attached scanned id card below", "ticket",
                "taxpan", "taxpan id", "tax id", "direct mobile", "contact email",
                "primary representative", "document reference"
            }
            if clean.lower() in noise_words:
                return False
            # Generic NER frequently tags uppercase document field headers
            # (EXPIRY, GENDER, DATE OF BIRTH) as ORG/LOCATION. Reject a
            # header-shaped line without maintaining a document-specific list.
            if clean.isupper() and len(clean) <= 32 and source_text:
                line_start = source_text.rfind("\n", 0, start) + 1
                line_end = source_text.find("\n", end)
                line = source_text[line_start:] if line_end < 0 else source_text[line_start:line_end]
                if re.fullmatch(r"[A-Z0-9][A-Z0-9 /_.()\-]*:?[ \t]*", line.strip()):
                    return False
            if self._is_non_pii_context(source_text, start, end, clean):
                return False
        return True

    @staticmethod
    def _is_non_pii_context(source_text: str, start: int, end: int, entity_text: str) -> bool:
        """Reject generic NER labels when the surrounding text is clearly a
        skills/list or technical-process context.

        This uses grammatical and layout signals rather than a technology
        allowlist, so unseen languages, libraries, tools, and frameworks are
        handled the same way as familiar ones.
        """
        line_start = source_text.rfind("\n", 0, start) + 1
        line_end = source_text.find("\n", end)
        line = source_text[line_start:] if line_end < 0 else source_text[line_start:line_end]
        relative_end = max(0, end - line_start)
        before = line[:relative_end].lower()
        lower_line = line.lower()

        skill_heading = re.search(
            r"\b(?:skills?|languages?|technologies?|frameworks?|coursework|tools?|libraries|platforms?)\b\s*:",
            lower_line,
        )
        list_like = "," in line or "|" in line or ";" in line
        technical_verb = re.search(
            r"\b(?:using|utilized|utilises|utilizes|integrated|implemented|developed|built|worked\s+with|configured|deployed|powered\s+by|managed)\b",
            lower_line,
        )
        academic_metric = re.search(r"\b(?:cgpa|gpa|percentage|credits?|semester|coursework)\b", lower_line)
        credential_field = re.search(r"\b(?:api\s*key|password|secret|access\s*token|bearer\s*token)\b\s*[:=]", lower_line)

        # A short entity inside a labelled comma-separated list is a skill,
        # not a person, place, or organization, regardless of its spelling.
        if skill_heading and list_like:
            return True
        if technical_verb and len(entity_text.split()) <= 4 and len(entity_text) <= 48:
            return True
        if academic_metric and len(entity_text.split()) <= 5:
            return True
        if credential_field and entity_text.strip().isupper() and len(entity_text.strip()) <= 16:
            return True

        # A single all-caps token in a list is generally an acronym/skill. Do
        # not suppress ordinary mixed-case names or multi-word organizations.
        if list_like and entity_text.strip().isupper() and len(entity_text.strip()) <= 12:
            return True
        return False

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
                if self._is_valid_entity(ent.text, pii_label, text, ent.start_char, ent.end_char):
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
