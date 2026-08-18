from typing import List, Dict, Any, Tuple
from pathlib import Path
import json

from pii_detector.masking.pii_masker import PIIMasker, MaskedResult
from pii_detector.schemas.entities import Entity


class MaskingAgent:
    """
    2. Masking Agent:
    Takes Human-in-the-Loop (HITL) verified PII entities,
    generates tokenized reversible masks <LABEL_ID>,
    and outputs masked document & secure mapping dictionary.
    """

    def __init__(self, token_format: str = "<{label}_{id}>"):
        self.masker = PIIMasker(token_format=token_format)

    def apply_hitl_masking(self, raw_text: str, verified_entities: List[Dict[str, Any]]) -> MaskedResult:
        """
        Filters approved entities from HITL review and applies masking.
        """
        entity_objects: List[Entity] = []

        for item in verified_entities:
            # Only include entities approved by Human-in-the-Loop review
            if item.get("approved") is True:
                label = item.get("user_custom_label") or item.get("label", "PII")
                entity_objects.append(
                    Entity(
                        text=item.get("text", ""),
                        label=label.upper().replace(" ", "_"),
                        start=item.get("start", 0),
                        end=item.get("end", 0),
                        confidence=item.get("confidence", 1.0),
                        source=item.get("source", "hitl_verified")
                    )
                )

        return self.masker.mask(raw_text, entity_objects, reuse_tokens=True)

    def save_masked_outputs(
        self,
        file_stem: str,
        masked_result: MaskedResult,
        output_dir: Path
    ) -> Tuple[Path, Path]:
        """Saves redacted text and mapping JSON to output directory."""
        output_dir.mkdir(parents=True, exist_ok=True)

        masked_file = output_dir / f"{file_stem}_masked.txt"
        masked_file.write_text(masked_result.masked_text, encoding="utf-8")

        mapping_file = output_dir / f"{file_stem}_mapping.json"
        mapping_data = {
            "file_stem": file_stem,
            "mapping": masked_result.mapping,
            "detailed_mapping": masked_result.detailed_mapping,
            "total_masked_tokens": len(masked_result.mapping)
        }
        with open(mapping_file, "w", encoding="utf-8") as f:
            json.dump(mapping_data, f, indent=4, ensure_ascii=False)

        return masked_file, mapping_file
