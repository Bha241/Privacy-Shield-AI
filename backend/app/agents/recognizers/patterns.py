import re

PATTERNS = {
    "PAN": re.compile(
        r"\b[A-Za-z]{5}\s?[0-9]{4}\s?[A-Za-z]\b|\b[A-Za-z]{3,5}[0-9]{4}[A-Za-z]\b",
        re.IGNORECASE
    ),
    "AADHAAR": re.compile(
        r"(?:\b\d{4}[-.\s]?\d{4}[-.\s]?\d{4}\b|\b\(\d{4}\)[-.\s]?\d{4}[-.\s]?\d{4}\b)"
    ),
    "PHONE": re.compile(
        r"(?:\+?\d{1,4}[-.\s]?)?(?:\(\d{2,5}\)[-.\s]?)?\b\d{3,5}[-.\s]?\d{3,5}\b|\b(?:\+?91[-.\s]?)?[5-9]\d{8,9}\b|\b(?:\+?\d{1,3}[-.\s]?)?\d{9,11}\b|\b(?:\+?91[-.\s]?)?\d{1,4}[X*]{2,8}\d{1,4}\b"
    ),
    "EMAIL": re.compile(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
    ),
    "TAX_ID": re.compile(
        r"\b(?:Taxpan|Tax\s*PAN|Tax\s*ID|PAN\s*ID|TIN|EIN)[:\s]+[A-Za-z0-9\-]{8,15}\b",
        re.IGNORECASE
    ),
    "IFSC": re.compile(
        r"\b[A-Za-z]{4}0[A-Za-z0-9]{6}\b"
    ),
    "ACCOUNT_NUMBER": re.compile(
        r"\b\d{9,18}\b"
    ),
    "UPI": re.compile(
        r"\b[a-zA-Z0-9._-]+@[a-zA-Z0-9.-]+\b"
    )
}