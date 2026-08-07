from dataclasses import dataclass

from pii_detector.schemas.entities import Entity


@dataclass
class DetectionResult:

    original_text: str

    regex_entities: list[Entity]

    llm_entities: list[Entity]

    all_entities: list[Entity]