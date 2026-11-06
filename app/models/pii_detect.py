"""
Lightweight, dependency-free PII (personally identifiable information)
detection via regex. Not exhaustive or locale-aware — a practical safety
net that catches common patterns (emails, phone numbers, credit-card-like
numbers, US SSN-like numbers) so they can be flagged for human review.

We deliberately return only the *type* of PII found (e.g. "email"), not the
matched value itself, to avoid echoing sensitive data back into audit-log
reasons or API responses.
"""
import re
from typing import List

_PATTERNS = {
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    "phone": re.compile(r"(?<!\d)(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}(?!\d)"),
    "credit_card": re.compile(r"\b(?:\d[ -]*?){13,16}\b"),
    "ssn_like": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
}


def detect_pii(text: str) -> List[str]:
    if not text:
        return []
    found = []
    for pii_type, pattern in _PATTERNS.items():
        if pattern.search(text):
            found.append(pii_type)
    return found
