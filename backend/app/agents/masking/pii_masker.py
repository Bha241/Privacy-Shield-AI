import json
from dataclasses import dataclass
from typing import List, Dict, Tuple
from pii_detector.schemas.entities import Entity


@dataclass
class MaskedResult:
    masked_text: str
    mapping: Dict[str, str]  # e.g. {"<NAME_1>": "Rahul Sharma"}
    detailed_mapping: List[Dict]  # full metadata list


class PIIMasker:
    """Masks detected PII entities in text and creates a reversible mapping dictionary."""

    def __init__(self, token_format: str = "<{label}_{id}>"):
        """
        Args:
            token_format: Format template for mask tokens, e.g. '<{label}_{id}>' or '[{label}_{id}]'
        """
        self.token_format = token_format

    def _resolve_overlaps(self, entities: List[Entity]) -> List[Entity]:
        """
        Sort entities by start position and resolve overlapping spans (keeping longer/first spans).
        """
        if not entities:
            return []

        # Sort by start offset ascending, then by length descending
        sorted_entities = sorted(entities, key=lambda e: (e.start, -(e.end - e.start)))

        resolved: List[Entity] = []
        last_end = -1

        for e in sorted_entities:
            # Skip invalid spans or overlapping spans
            if e.start >= last_end and e.end > e.start:
                resolved.append(e)
                last_end = e.end

        return resolved

    def mask(self, text: str, entities: List[Entity], reuse_tokens: bool = True) -> MaskedResult:
        """
        Mask PII entities in text.

        Args:
            text: Original input text
            entities: List of detected Entity objects
            reuse_tokens: If True, identical text values for the same label reuse the same mask token.

        Returns:
            MaskedResult containing masked_text, mapping dict, and detailed_mapping metadata list.
        """
        resolved_entities = self._resolve_overlaps(entities)

        label_counters: Dict[str, int] = {}
        text_to_token: Dict[Tuple[str, str], str] = {}
        mapping: Dict[str, str] = {}
        detailed_mapping: List[Dict] = []

        masked_chars = list(text)
        entity_token_pairs: List[Tuple[Entity, str]] = []

        for e in resolved_entities:
            key = (e.label, e.text)
            if reuse_tokens and key in text_to_token:
                token = text_to_token[key]
            else:
                label_counters[e.label] = label_counters.get(e.label, 0) + 1
                token_id = label_counters[e.label]
                token = self.token_format.format(label=e.label, id=token_id)
                if reuse_tokens:
                    text_to_token[key] = token

            mapping[token] = e.text

            detailed_mapping.append({
                "mask_token": token,
                "original_text": e.text,
                "label": e.label,
                "start": e.start,
                "end": e.end,
                "confidence": getattr(e, "confidence", 1.0),
                "source": getattr(e, "source", "unknown"),
            })

            entity_token_pairs.append((e, token))

        # Perform string replacements from last offset to first offset to prevent index drift
        for e, token in reversed(entity_token_pairs):
            masked_chars[e.start:e.end] = list(token)

        masked_text = "".join(masked_chars)

        return MaskedResult(
            masked_text=masked_text,
            mapping=mapping,
            detailed_mapping=detailed_mapping,
        )

    def unmask(self, masked_text: str, mapping: Dict[str, str]) -> str:
        """
        Restore original text from masked text using the mapping dictionary.
        """
        unmasked = masked_text
        for token, original_val in mapping.items():
            unmasked = unmasked.replace(token, original_val)
        return unmasked
