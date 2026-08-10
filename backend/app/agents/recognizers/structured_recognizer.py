"""Context-aware, format-tolerant detection for dates and postal addresses."""

from __future__ import annotations

import re
from datetime import date, datetime

from pii_detector.schemas.entities import Entity


class StructuredRecognizer:
    """Detect structured PII without relying on document-specific examples.

    Date values are validated instead of matched by shape alone. Address
    extraction is context- and boundary-aware, so it supports different field
    ordering and multi-component values while stopping at the next field.
    """

    _date_value = (
        r"(?:"
        r"\d{4}[./-]\d{1,2}[./-]\d{1,2}|"
        r"\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|"
        r"\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]{3,12}\s+\d{2,4}|"
        r"[A-Za-z]{3,12}\s+\d{1,2}(?:st|nd|rd|th)?[,]?\s+\d{2,4}"
        r")"
    )
    _date_context_before = re.compile(
        rf"(?is)\b(?:date\s+of\s+birth|birth\s+date|dob|born(?:\s+on)?)\b\s*(?:is|was|on|:|=|-)?\s*(?P<value>{_date_value})"
    )
    _date_context_after = re.compile(
        rf"(?is)(?P<value>{_date_value})\s*(?:,?\s*)\b(?:date\s+of\s+birth|birth\s+date|dob)\b"
    )
    _address_context = re.compile(
        r"(?is)\b(?:residential|permanent|current|mailing|home|office)?\s*address\b\s*(?:is|:|=|-)?\s*(?P<value>[^\r\n;|]{6,220})"
    )
    _address_component_line = re.compile(
        r"(?im)^(?P<value>[^\r\n]{6,220}(?:\b(?:street|st\.?|road|rd\.?|lane|ln\.?|avenue|ave\.?|boulevard|blvd\.?|block|sector|flat|apartment|apt\.?|house|plot|village|district|postcode|pincode|zip|zip\s*code)\b|\b\d{5,6}\b)[^\r\n]*)$"
    )
    _field_boundary = re.compile(
        r"(?i)\s+(?=(?:full\s+name|name|dob|date\s+of\s+birth|phone|mobile|email|pan|aadhaar|passport|address|city|state|country|pin\s*code|pincode)\s*[:=-])"
    )

    def recognize(self, text: str) -> list[Entity]:
        return self._date_entities(text) + self._address_entities(text)

    def _date_entities(self, text: str) -> list[Entity]:
        entities: list[Entity] = []
        seen: set[tuple[int, int]] = set()
        for pattern in (self._date_context_before, self._date_context_after):
            for match in pattern.finditer(text):
                value = match.group("value")
                start, end = match.span("value")
                if (start, end) in seen or not self._valid_date(value):
                    continue
                seen.add((start, end))
                entities.append(Entity(value.strip(), "DATE_OF_BIRTH", start, end, 0.99, "regex_structured"))
        return entities

    def _address_entities(self, text: str) -> list[Entity]:
        entities: list[Entity] = []
        seen: set[tuple[int, int]] = set()
        for match in self._address_context.finditer(text):
            value, start, end = self._clean_address(match.group("value"), *match.span("value"), text=text)
            if value and (start, end) not in seen:
                seen.add((start, end))
                entities.append(Entity(value, "ADDRESS", start, end, 0.97, "regex_structured"))

        for match in self._address_component_line.finditer(text):
            # Explicitly labelled fields are handled by the context matcher;
            # do not let a later street keyword make the entire mixed field
            # line look like one address.
            if re.search(r"(?i)\b(?:address|date\s+of\s+birth|dob)\b", match.group("value")):
                continue
            value, start, end = self._clean_address(match.group("value"), *match.span("value"), text=text)
            if value and (start, end) not in seen and self._looks_like_address(value):
                seen.add((start, end))
                entities.append(Entity(value, "ADDRESS", start, end, 0.88, "regex_structured"))
        return entities

    def _clean_address(self, value: str, start: int, end: int, *, text: str) -> tuple[str, int, int]:
        value = value.strip()
        leading_label = re.match(
            r"(?is)^(?:residential|permanent|current|mailing|home|office)?\s*address\b\s*(?:is|:|=|-)?\s*",
            value,
        )
        if leading_label:
            shift = leading_label.end()
            start += shift
            value = value[shift:]
        delimiter = re.search(r"[;|]", value)
        if delimiter:
            value = value[:delimiter.start()]
        value = value.strip().strip(",.;:-")
        # Stop a labelled value before the next labelled field when fields are
        # written on one line in arbitrary order.
        boundary = self._field_boundary.search(value)
        if boundary:
            value = value[:boundary.start()].rstrip(" ,.;:-")
        return value, start, start + len(value)

    @staticmethod
    def _looks_like_address(value: str) -> bool:
        words = re.findall(r"[A-Za-z0-9]+", value)
        has_number = bool(re.search(r"\d", value))
        has_separator = bool(re.search(r"[,/]", value))
        has_street_marker = bool(re.search(
            r"(?i)\b(?:street|st\.?|road|rd\.?|lane|ln\.?|avenue|ave\.?|boulevard|blvd\.?|block|sector|flat|apartment|apt\.?|house|plot|village|district)\b",
            value,
        ))
        has_postal_shape = bool(re.search(r"\b\d{5,6}\b", value))
        return len(words) >= 3 and has_number and (has_street_marker or (has_postal_shape and has_separator))

    @staticmethod
    def _valid_date(value: str) -> bool:
        normalized = re.sub(r"(?i)(\d)(st|nd|rd|th)\b", r"\1", value.strip().replace(",", ""))
        formats = ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%m-%d-%Y", "%d.%m.%Y", "%d %B %Y", "%d %b %Y", "%B %d %Y", "%b %d %Y", "%B %d %Y")
        parsed: datetime | None = None
        for fmt in formats:
            try:
                parsed = datetime.strptime(normalized, fmt)
                break
            except ValueError:
                continue
        if parsed is None:
            # Two-digit years are accepted only when Python can parse them
            # unambiguously; this avoids treating arbitrary numeric IDs as DOBs.
            for fmt in ("%d/%m/%y", "%m/%d/%y", "%d-%m-%y", "%m-%d-%y"):
                try:
                    parsed = datetime.strptime(normalized, fmt)
                    break
                except ValueError:
                    continue
        if parsed is None:
            return False
        return date(1900, 1, 1) <= parsed.date() <= date.today()
