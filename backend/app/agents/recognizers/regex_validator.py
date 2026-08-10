"""Format validators used after regex candidates are found."""

from __future__ import annotations

import re


def is_valid_aadhaar(value: str) -> bool:
    cleaned = re.sub(r"[\s\-.]", "", value or "")
    return len(cleaned) == 12 and cleaned[0] in "23456789" and cleaned.isdigit()


def is_valid_pan(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Z]{5}[0-9]{4}[A-Z]", (value or "").replace(" ", "").upper()))


def is_valid_gstin(value: str) -> bool:
    return bool(re.fullmatch(r"[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]", (value or "").upper()))


def is_valid_ifsc(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Z]{4}0[A-Z0-9]{6}", (value or "").upper()))
