from pii_detector.recognizers.regex_recognizer import RegexRecognizer
from pii_detector.recognizers.spacy_recognizer import SpacyRecognizer
from pii_detector.schemas.detection_results import DetectionResult


class PIIDetector:

    def __init__(self, enable_llm: bool = False):

        self.regex = RegexRecognizer()
        self.spacy = SpacyRecognizer()
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
        # Sort by confidence descending, regex source priority, then start offset ascending
        sorted_ents = sorted(
            entities,
            key=lambda e: (
                -getattr(e, "confidence", 0.9),
                0 if "regex" in getattr(e, "source", "") else 1,
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

    def detect(self, text, use_llm_residual: bool = True, domain: str = "general"):
        regex_entities = self.regex.recognize(text, domain=domain)
        spacy_entities = self.spacy.recognize(text)

        llm_entities = []
        if self.enable_llm:
            combined = regex_entities + spacy_entities
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

        all_raw = regex_entities + spacy_entities + llm_entities
        deduped_entities = self._deduplicate_entities(all_raw)

        return DetectionResult(
            original_text=text,
            regex_entities=regex_entities + spacy_entities,
            llm_entities=llm_entities,
            all_entities=deduped_entities
        )