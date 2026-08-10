"""Optional Presidio-based recognizer adapted from the supplied detector."""

from __future__ import annotations

import logging
import os
import re
from typing import Any

from pii_detector.schemas.entities import Entity

logger = logging.getLogger(__name__)

AnalyzerEngine = Pattern = PatternRecognizer = RecognizerRegistry = NlpEngineProvider = None
PRESIDIO_AVAILABLE = None


class PresidioRecognizer:
    """Lazy Presidio recognizer used as the primary Fast-mode engine."""

    LABEL_MAP = {
        "PERSON": "NAME", "NRP": "NAME", "ORGANIZATION": "ORGANIZATION",
        "LOCATION": "LOCATION", "GPE": "LOCATION", "LOC": "LOCATION",
        "FAC": "LOCATION", "ADDRESS": "ADDRESS", "MONEY": "MONEY",
        "EMAIL_ADDRESS": "EMAIL", "PHONE_NUMBER": "PHONE",
        "CREDIT_CARD": "CREDIT_CARD", "IBAN_CODE": "IBAN",
        "IP_ADDRESS": "IP_ADDRESS", "DATE_TIME": "DATE", "URL": "URL",
        "IN_PAN": "PAN", "IN_GSTIN": "GSTIN", "IN_IFSC": "IFSC",
        "IN_AADHAAR": "AADHAAR", "IN_ADDRESS": "ADDRESS",
    }

    def __init__(self, model_name: str = "en_core_web_sm", score_threshold: float = 0.4):
        self.model_name = model_name
        self.score_threshold = score_threshold
        self._analyzer: Any | None = None
        self._failed = False

    @staticmethod
    def _load_dependencies() -> bool:
        global AnalyzerEngine, Pattern, PatternRecognizer, RecognizerRegistry, NlpEngineProvider, PRESIDIO_AVAILABLE
        if os.getenv("PRIVACYSHIELD_ENABLE_PRESIDIO", "false").strip().lower() not in {"1", "true", "yes", "on"}:
            PRESIDIO_AVAILABLE = False
            return False
        if PRESIDIO_AVAILABLE is not None:
            return bool(PRESIDIO_AVAILABLE)
        try:
            from presidio_analyzer import AnalyzerEngine as _AnalyzerEngine
            from presidio_analyzer import Pattern as _Pattern
            from presidio_analyzer import PatternRecognizer as _PatternRecognizer
            from presidio_analyzer import RecognizerRegistry as _RecognizerRegistry
            from presidio_analyzer.nlp_engine import NlpEngineProvider as _NlpEngineProvider
            AnalyzerEngine = _AnalyzerEngine
            Pattern = _Pattern
            PatternRecognizer = _PatternRecognizer
            RecognizerRegistry = _RecognizerRegistry
            NlpEngineProvider = _NlpEngineProvider
            PRESIDIO_AVAILABLE = True
        except Exception as exc:
            PRESIDIO_AVAILABLE = False
            logger.info("Presidio is unavailable; using the Fast-mode compatibility detector: %s", exc)
        return bool(PRESIDIO_AVAILABLE)

    @property
    def available(self) -> bool:
        return self._load_dependencies() and not self._failed

    def _build_analyzer(self):
        if not self._load_dependencies():
            return None
        try:
            provider = NlpEngineProvider(nlp_configuration={
                "nlp_engine_name": "spacy",
                "models": [{"lang_code": "en", "model_name": self.model_name}],
            })
            nlp_engine = provider.create_engine()
            registry = RecognizerRegistry()
            registry.load_predefined_recognizers(nlp_engine=nlp_engine)

            custom = [
                ("IN_PAN", r"\b[A-Z]{5}[0-9]{4}[A-Z]\b", "PAN", 0.9, ["pan", "permanent account"]),
                ("IN_GSTIN", r"\b[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b", "GSTIN", 0.9, ["gstin", "gst"]),
                ("IN_IFSC", r"\b[A-Z]{4}0[A-Z0-9]{6}\b", "IFSC", 0.85, ["ifsc", "bank", "neft", "rtgs"]),
                ("IN_AADHAAR", r"\b[2-9][0-9]{3}[\s-]?[0-9]{4}[\s-]?[0-9]{4}\b", "Aadhaar", 0.7, ["aadhaar", "aadhar", "uidai"]),
            ]
            for entity, regex, name, score, context in custom:
                registry.add_recognizer(PatternRecognizer(
                    supported_entity=entity,
                    name=f"PrivacyShield{name}Recognizer",
                    patterns=[Pattern(name, regex, score)],
                    context=context,
                ))

            return AnalyzerEngine(registry=registry, nlp_engine=nlp_engine, supported_languages=["en"])
        except Exception as exc:
            self._failed = True
            logger.warning("Presidio Fast-mode recognizer unavailable: %s", exc)
            return None

    @property
    def analyzer(self):
        if self._analyzer is None and not self._failed:
            self._analyzer = self._build_analyzer()
        return self._analyzer

    def recognize(self, text: str) -> list[Entity]:
        if not text or not text.strip() or self.analyzer is None:
            return []
        try:
            results = self.analyzer.analyze(text=text, language="en", score_threshold=self.score_threshold)
        except Exception as exc:
            self._failed = True
            logger.warning("Presidio Fast-mode recognition failed: %s", exc)
            return []

        entities: list[Entity] = []
        seen: set[tuple[int, int, str]] = set()
        for result in results:
            label = self.LABEL_MAP.get(result.entity_type, result.entity_type)
            key = (result.start, result.end, label)
            if key in seen:
                continue
            seen.add(key)
            value = text[result.start:result.end]
            if not value.strip() or (label in {"NAME", "ORGANIZATION", "LOCATION"} and value.strip().isupper() and len(value.strip()) <= 32):
                continue
            entities.append(Entity(
                text=value,
                label=label,
                start=result.start,
                end=result.end,
                confidence=round(float(result.score), 3),
                source="presidio",
            ))
        return sorted(entities, key=lambda entity: (entity.start, -(entity.end - entity.start)))
