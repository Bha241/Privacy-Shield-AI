from pii_detector.recognizers.regex_loader import RegexLoader
from pii_detector.recognizers.regex_validator import (
    is_valid_aadhaar,
    is_valid_gstin,
    is_valid_ifsc,
    is_valid_pan,
)
from pii_detector.schemas.entities import Entity


class RegexRecognizer:

    def __init__(self):
        self.loader = RegexLoader()

    def recognize(self, text, domain: str = "general"):
        patterns = self.loader.get_patterns(domain=domain)
        entities = []

        for label, info in patterns.items():
            pattern = info["regex"]
            confidence = info["confidence"]

            for match in pattern.finditer(text):
                val = None
                start = None
                end = None
                if match.lastindex and match.lastindex >= 1:
                    for g_idx in range(1, match.lastindex + 1):
                        if match.group(g_idx) is not None:
                            val = match.group(g_idx)
                            start = match.start(g_idx)
                            end = match.end(g_idx)
                            break

                if val is None:
                    val = match.group()
                    start = match.start()
                    end = match.end()

                if val and val.strip():
                    clean_val = val.strip()
                    if label == "AADHAAR" and not is_valid_aadhaar(clean_val):
                        continue
                    if label == "PAN" and not is_valid_pan(clean_val):
                        continue
                    if label == "GSTIN" and not is_valid_gstin(clean_val):
                        continue
                    if label == "IFSC" and not is_valid_ifsc(clean_val):
                        continue
                    clean_end = end
                    if label == "NAME":
                        words = clean_val.split()
                        acronyms = {"pan", "aadhaar", "dob", "email", "phone", "gstin", "ifsc", "ssn", "tin", "ein", "id", "has", "is", "was", "visited", "visited apollo"}
                        while len(words) > 1 and words[-1].lower() in acronyms:
                            words.pop()
                        clean_val = " ".join(words)
                        clean_end = start + len(clean_val)

                    entities.append(
                        Entity(
                            text=clean_val,
                            label=label,
                            start=start,
                            end=clean_end,
                            confidence=confidence,
                            source=f"regex_{domain}" if domain and domain != "general" else "regex"
                        )
                    )

        return entities
