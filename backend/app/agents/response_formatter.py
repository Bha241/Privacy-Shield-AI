"""
PrivacyShieldAI - Response Formatter & Quality Review Engine
Converts raw LLM outputs into natural, conversational, ChatGPT/Claude/Gemini-style responses.
Strips robotic extraction labels, eliminates overused AI cliches, formats intent-specific outputs,
and applies a self-review pass before output delivery.
"""

import re
from typing import Optional


class ResponseFormatter:
    """
    Intelligent response formatting and quality assurance engine.
    """

    ROBOTIC_LABELS = [
        r"^\s*Document Header\s*:?",
        r"^\s*Key Information\s*:?",
        r"^\s*Privacy Summary\s*:?",
        r"^\s*Detected PII\s*:?",
        r"^\s*Extraction Results\s*:?",
        r"^\s*Extracted Fields\s*:?",
        r"^\s*PII Entities\s*:?",
        r"^\s*Raw Context\s*:?",
        r"^\s*Compliance\.\s*$",
        r"^\s*\[Sanitized Response\]\s*:?",
        r"^\s*Privacy Guarantee\s*:?",
    ]

    # AI Cliches and disclaimers to remove during quality review
    AI_CLICHE_REPLACEMENTS = [
        (r"^Based on available (document )?excerpts,?\s*", ""),
        (r"^Based on (the )?retrieved context,?\s*", ""),
        (r"^The available context indicates that\s*", ""),
        (r"^This document is (designed|intended) to\s+", "This document "),
        (r"^The primary purpose of this document is to\s+", "This document "),
        (r"^This document contains\s+", "This record includes "),
        (r"\bFurthermore,\s*", ""),
        (r"\bMoreover,\s*", ""),
        (r"\bAdditionally,\s*", ""),
        (r"\bIn conclusion,\s*", ""),
        (r"\bOverall,\s*", ""),
    ]

    @classmethod
    def strip_robotic_labels(cls, text: str) -> str:
        """Strips robotic label headers and formatting artifacts from LLM responses."""
        if not text:
            return text

        lines = text.splitlines()
        cleaned_lines = []

        for line in lines:
            stripped = line.strip()

            is_robotic = False
            for pattern in cls.ROBOTIC_LABELS:
                if re.search(pattern, stripped, flags=re.IGNORECASE):
                    is_robotic = True
                    break

            if is_robotic:
                continue

            cleaned_lines.append(line)

        cleaned_text = "\n".join(cleaned_lines)
        cleaned_text = re.sub(r"\n{3,}", "\n\n", cleaned_text).strip()
        return cleaned_text

    @classmethod
    def clean_ai_cliches(cls, text: str) -> str:
        """Removes overused AI opening lines and repetitive transition words."""
        if not text:
            return text

        cleaned = text
        for pattern, replacement in cls.AI_CLICHE_REPLACEMENTS:
            cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)

        return cleaned.strip()

    @classmethod
    def quality_review(cls, text: str, intent: str) -> str:
        """
        Self-review pass evaluating response quality.
        Rejects or repairs responses that contain raw label dumps or excessive AI phrasing.
        """
        if not text:
            return text

        reviewed = text

        # 1. Clean robotic labels & cliches
        reviewed = cls.strip_robotic_labels(reviewed)
        reviewed = cls.clean_ai_cliches(reviewed)

        # 2. Fix double punctuation or double whitespace artifacts
        reviewed = re.sub(r"\s{2,}", " ", reviewed)
        reviewed = re.sub(r"\n\s+\n", "\n\n", reviewed)

        return reviewed.strip()

    @classmethod
    def format_response(
        cls,
        raw_text: str,
        intent: str,
        query: str,
        confidence: str = "high"
    ) -> str:
        """
        Main response formatting pipeline based on query intent and retrieval confidence.
        Ensures response matches ChatGPT / Claude / Gemini quality.
        """
        if not raw_text or not raw_text.strip():
            return raw_text

        # 1. Initial cleanup & quality review
        cleaned = cls.quality_review(raw_text, intent)

        # 2. Confidence-aware tone framing (only apply prefix if model did not already express confidence)
        if confidence == "medium" and not any(k in cleaned.lower() for k in ["indicates", "suggests", "according to"]):
            if intent in ["question", "summary"]:
                cleaned = f"Based on the document context, {cleaned[0].lower() + cleaned[1:] if len(cleaned) > 1 else cleaned}"
        elif confidence == "low" and not any(k in cleaned.lower() for k in ["based on", "retrieved", "limited"]):
            cleaned = f"Based on available document excerpts, {cleaned[0].lower() + cleaned[1:] if len(cleaned) > 1 else cleaned}"

        # 3. Intent-specific post-processing
        if intent == "question":
            if not any(k in query.lower() for k in ["section", "breakdown", "list"]):
                cleaned = re.sub(r"^###?\s*(Answer|Response|Result)\s*\n+", "", cleaned, flags=re.IGNORECASE).strip()

        elif intent == "summary":
            cleaned = re.sub(r"^###?\s*(Summary|Executive Summary)\s*\n+", "", cleaned, flags=re.IGNORECASE).strip()
            if not any(k in query.lower() for k in ["privacy", "compliance", "dpdp", "pii"]):
                cleaned = re.sub(r"###?\s*(Compliance|Privacy Considerations|DPDP).*$", "", cleaned, flags=re.DOTALL | re.IGNORECASE).strip()

        elif intent == "analysis":
            cleaned = re.sub(r"([^\n])\n(###\s+)", r"\1\n\n\2", cleaned)

        elif intent == "compliance":
            cleaned = re.sub(r"([^\n])\n(###\s+)", r"\1\n\n\2", cleaned)

        elif intent == "comparison":
            cleaned = re.sub(r"([^\n])\n(###\s+)", r"\1\n\n\2", cleaned)

        return cleaned.strip()
