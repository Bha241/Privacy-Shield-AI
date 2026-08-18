"""
Privacy Leakage Checker for PrivacyShield AI.

Evaluates whether raw, unmasked PII appears in:
1. Context sent to the LLM (context leakage)
2. Final generated answer returned to the user or downstream systems (answer leakage)

Provides high-precision detection, detailed leakage reports, and exception assertions.
"""

from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional, Set
import re

from .pii_patterns import PII_PATTERNS, MASKED_TOKEN_PATTERN, PII_TYPE_DESCRIPTIONS


class PrivacyLeakageError(Exception):
    """Raised when raw PII leakage is detected in context or LLM response."""
    def __init__(self, message: str, report: Optional["LeakageReport"] = None):
        super().__init__(message)
        self.report = report


@dataclass
class PIIEntity:
    """Represents an identified raw PII entity occurrence in text."""
    entity_type: str
    raw_value: str
    start: int
    end: int
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class LeakageReport:
    """Detailed summary of context and answer privacy leakage inspection."""
    context_leakage: bool
    answer_leakage: bool
    context_hits: List[Dict[str, Any]]
    answer_hits: List[Dict[str, Any]]
    is_safe: bool
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _get_masked_spans(text: str) -> List[tuple]:
    """Finds all character spans that contain valid masked tokens/placeholders."""
    return [match.span() for match in MASKED_TOKEN_PATTERN.finditer(text)]


def _is_inside_masked_span(start: int, end: int, masked_spans: List[tuple]) -> bool:
    """Checks if a detected match is fully or partially inside a legitimate masked placeholder."""
    for m_start, m_end in masked_spans:
        if (start >= m_start and start < m_end) or (end > m_start and end <= m_end):
            return True
        if m_start >= start and m_end <= end:
            return True
    return False


def find_raw_pii(
    text: str,
    target_types: Optional[Set[str]] = None,
    allow_masked_tokens: bool = True
) -> List[PIIEntity]:
    """
    Scans a given text string for raw, unmasked PII entities using regex patterns.

    Args:
        text: The input text to inspect (context string or answer string).
        target_types: Optional set of specific PII types to look for (e.g. {'PAN', 'PHONE'}).
                     If None, checks all known PII patterns.
        allow_masked_tokens: When True, excludes matches enclosed inside valid masked
                            tokens like [PHONE_1], [PAN_1], etc.

    Returns:
        List of PIIEntity objects containing detected raw PII values, types, and character spans.
    """
    if not text or not isinstance(text, str):
        return []

    hits: List[PIIEntity] = []
    masked_spans = _get_masked_spans(text) if allow_masked_tokens else []
    seen_spans: Set[tuple] = set()

    # Sort candidate hits by span length descending (longer, more specific spans first)
    raw_hits = []
    for pii_type, pattern in PII_PATTERNS.items():
        if target_types and pii_type not in target_types:
            continue

        for match in pattern.finditer(text):
            span = match.span()
            matched_value = match.group(0).strip()

            if not matched_value:
                continue

            if allow_masked_tokens and _is_inside_masked_span(span[0], span[1], masked_spans):
                continue

            raw_hits.append(
                PIIEntity(
                    entity_type=pii_type,
                    raw_value=matched_value,
                    start=span[0],
                    end=span[1],
                    description=PII_TYPE_DESCRIPTIONS.get(pii_type, pii_type)
                )
            )

    # Sort so that longer/specific matches take precedence and remove sub-spans
    raw_hits.sort(key=lambda x: (-(x.end - x.start), x.start))
    filtered_hits: List[PIIEntity] = []
    claimed_intervals: List[tuple] = []

    for hit in raw_hits:
        # Check if this hit is entirely contained inside a previously claimed larger span
        is_subspan = any(c_start <= hit.start and hit.end <= c_end for c_start, c_end in claimed_intervals)
        if not is_subspan:
            filtered_hits.append(hit)
            claimed_intervals.append((hit.start, hit.end))

    # Sort final hits chronologically by start index
    filtered_hits.sort(key=lambda x: x.start)
    return filtered_hits


def is_safe_text(text: str) -> bool:
    """Returns True if the text contains zero raw unmasked PII, False otherwise."""
    return len(find_raw_pii(text)) == 0


def leakage_report(
    context: str,
    answer: str,
    target_types: Optional[Set[str]] = None
) -> Dict[str, Any]:
    """
    Generates a complete privacy leakage evaluation report for context sent to LLM
    and the final answer returned to the user.

    Args:
        context: The prompt/retrieved context string (should be masked).
        answer: The generated answer string.
        target_types: Optional subset of PII types to evaluate.

    Returns:
        Dictionary with:
        - context_leakage: bool
        - answer_leakage: bool
        - context_hits: List[Dict]
        - answer_hits: List[Dict]
        - is_safe: bool
        - summary: human-readable message
    """
    ctx_hits_obj = find_raw_pii(context, target_types=target_types)
    ans_hits_obj = find_raw_pii(answer, target_types=target_types)

    ctx_hits = [h.to_dict() for h in ctx_hits_obj]
    ans_hits = [h.to_dict() for h in ans_hits_obj]

    has_context_leak = len(ctx_hits) > 0
    has_answer_leak = len(ans_hits) > 0
    is_safe = (not has_context_leak) and (not has_answer_leak)

    if is_safe:
        summary_msg = "CLEAN: Zero raw PII detected in context and answer."
    else:
        issues = []
        if has_context_leak:
            types = set(h["entity_type"] for h in ctx_hits)
            issues.append(f"{len(ctx_hits)} raw PII entities in context ({', '.join(types)})")
        if has_answer_leak:
            types = set(h["entity_type"] for h in ans_hits)
            issues.append(f"{len(ans_hits)} raw PII entities in answer ({', '.join(types)})")
        summary_msg = f"PRIVACY VIOLATION: {'; '.join(issues)}."

    report_obj = LeakageReport(
        context_leakage=has_context_leak,
        answer_leakage=has_answer_leak,
        context_hits=ctx_hits,
        answer_hits=ans_hits,
        is_safe=is_safe,
        summary=summary_msg,
    )
    return report_obj.to_dict()


def assert_no_leakage(context: str, answer: str, target_types: Optional[Set[str]] = None) -> None:
    """
    Asserts that no raw PII is present in context or answer.
    Raises PrivacyLeakageError if any leakage is discovered. Useful in unit tests and pipeline guards.
    """
    report = leakage_report(context, answer, target_types=target_types)
    if not report["is_safe"]:
        raise PrivacyLeakageError(
            f"Privacy Leakage Assertion Failed: {report['summary']}",
            report=LeakageReport(**report)
        )
