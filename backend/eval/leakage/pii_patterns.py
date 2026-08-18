"""
PII Regex Patterns for PrivacyShield AI Evaluation & Leakage Verification.

Covers standard Indian and international PII entities:
- PHONE (Indian mobile + landline + international formats)
- EMAIL (Standard RFC 5322 compliant address format)
- PAN (Indian Permanent Account Number: 5 letters + 4 digits + 1 letter)
- AADHAAR (Indian 12-digit UIDAI number with standard space/hyphen delimiters)
- GSTIN (Indian Goods and Services Tax Identification Number: 15 alphanumeric)
- UPI (Unified Payments Interface VPA handle, e.g. name@okaxis, user@upi)
- PASSPORT (Indian / International passport identifier)
- CREDIT_CARD (Major network cards: Visa, Mastercard, RuPay, Amex)
- IFSC (Indian Financial System Code: 4 alphabetic + '0' + 6 alphanumeric)
- BANK_ACCOUNT (Standard 9-18 digit account numbers)
"""

import re
from typing import Dict, Pattern

# Compiled high-precision regex patterns for raw PII detection
PII_PATTERNS: Dict[str, Pattern] = {
    "PAN": re.compile(
        r"\b[A-Z]{5}[0-9]{4}[A-Z]\b",
        re.IGNORECASE
    ),
    "AADHAAR": re.compile(
        r"\b[2-9]\d{3}[-\s]\d{4}[-\s]\d{4}\b|\b[2-9]\d{11}\b"
    ),
    "PHONE": re.compile(
        r"(?:\+?91[\-\s]?)?[6-9]\d{4}[\-\s]?\d{5}\b|"
        r"\b(?:\+?1[\-\s]?)?\(?\d{3}\)?[\-\s]?\d{3}[\-\s]?\d{4}\b|"
        r"\b\d{3,5}[\-\s]\d{6,8}\b"
    ),
    "EMAIL": re.compile(
        r"\b[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+\b"
    ),
    "GSTIN": re.compile(
        r"\b\d{2}[A-Z]{5}\d{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}\b",
        re.IGNORECASE
    ),
    "UPI": re.compile(
        r"\b[a-zA-Z0-9._-]+@(okaxis|okhdfcbank|okicici|oksbi|paytm|upi|apl|ybl|axl|ibl|barodampay|pnb|federal)\b",
        re.IGNORECASE
    ),
    "PASSPORT": re.compile(
        r"\b[A-PR-WYa-pr-wy][1-9]\d{6}\b"
    ),
    "CREDIT_CARD": re.compile(
        r"\b(?:\d{4}[-\s]?){3}\d{4}\b|\b\d{16}\b"
    ),
    "IFSC": re.compile(
        r"\b[A-Z]{4}0[A-Z0-9]{6}\b",
        re.IGNORECASE
    ),
    "BANK_ACCOUNT": re.compile(
        r"\b(?<!\d)\d{9,18}(?!\d)\b"
    )
}

# Human-readable labels and descriptions
PII_TYPE_DESCRIPTIONS: Dict[str, str] = {
    "PAN": "Indian Permanent Account Number (10-char alphanumeric)",
    "AADHAAR": "Indian UIDAI Aadhaar Number (12 digits)",
    "PHONE": "Phone / Mobile Number (Indian/International)",
    "EMAIL": "Email Address",
    "GSTIN": "Goods and Services Tax Identification Number (15-char)",
    "UPI": "Unified Payments Interface (UPI) VPA",
    "PASSPORT": "Passport Number",
    "CREDIT_CARD": "Credit/Debit Card Number (16 digits)",
    "IFSC": "Indian Financial System Code (11-char)",
    "BANK_ACCOUNT": "Bank Account Number (9-18 digits)",
}

# Masked token pattern to filter out false positives
MASKED_TOKEN_PATTERN = re.compile(
    r"\[(?:MASKED_)?(?:PHONE|EMAIL|PAN|AADHAAR|GSTIN|UPI|NAME|PERSON|ORG|DATE|ADDRESS|ACCOUNT|IFSC|SSN|PII|ID|LOC|GPE)(?:_[A-Za-z0-9]+)?\]|"
    r"\[[A-Z0-9_]+_\d+\]|"
    r"\*{3,}[0-9A-Za-z\-]*|"
    r"X{3,}[0-9A-Za-z\-]*",
    re.IGNORECASE
)
