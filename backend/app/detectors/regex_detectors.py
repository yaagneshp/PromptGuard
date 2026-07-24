import re
from dataclasses import dataclass, field
from typing import Callable, Optional


def _luhn_valid(digits: str) -> bool:
    total = 0
    reverse_digits = digits[::-1]
    for i, d in enumerate(reverse_digits):
        n = int(d)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def _credit_card_validator(match: str) -> bool:
    digits = re.sub(r"[\s-]", "", match)
    return 13 <= len(digits) <= 19 and _luhn_valid(digits)


# (category, compiled pattern, optional post-match validator)
DETECTOR_REGISTRY: list[tuple[str, re.Pattern, Optional[Callable[[str], bool]]]] = [
    (
        "email",
        re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
        None,
    ),
    (
        "uk_phone",
        re.compile(r"(?<!\d)(?:\+44\s?|0)\d(?:\s?\d){9}(?!\d)"),
        None,
    ),
    (
        "ni_number",
        re.compile(
            r"\b[A-CEGHJ-PR-TW-Z][A-CEGHJ-NPR-TW-Z]\s?\d{2}\s?\d{2}\s?\d{2}\s?[A-D]\b",
            re.IGNORECASE,
        ),
        None,
    ),
    (
        "credit_card",
        re.compile(r"\b\d(?:[ -]?\d){12,18}\b"),
        _credit_card_validator,
    ),
    (
        "aws_key",
        re.compile(r"\b(?:AKIA|ASIA|AROA|AIDA)[0-9A-Z]{16}\b"),
        None,
    ),
    (
        "ip_address",
        re.compile(
            r"\b(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}"
            r"(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\b"
        ),
        None,
    ),
    (
        "token_url",
        re.compile(
            r"https?://\S+?[?&](?:token|api[_-]?key|access[_-]?token|secret|auth|session)=[^\s&]+",
            re.IGNORECASE,
        ),
        None,
    ),
]


@dataclass
class ScanResult:
    redacted_text: str
    category_counts: dict[str, int] = field(default_factory=dict)
    raw_char_count: int = 0


def scan_text(text: str) -> ScanResult:
    """Scan text for PII, returning a redacted copy plus per-category match counts.

    The original text is never returned or logged — callers should discard it
    once this function has run.
    """
    raw_matches: list[tuple[str, int, int]] = []
    for category, pattern, validator in DETECTOR_REGISTRY:
        for m in pattern.finditer(text):
            if validator is not None and not validator(m.group(0)):
                continue
            raw_matches.append((category, m.start(), m.end()))

    # Resolve overlaps: earliest start wins, ties broken by longest match
    raw_matches.sort(key=lambda t: (t[1], -(t[2] - t[1])))
    resolved: list[tuple[str, int, int]] = []
    last_end = -1
    for category, start, end in raw_matches:
        if start >= last_end:
            resolved.append((category, start, end))
            last_end = end

    counts: dict[str, int] = {}
    parts: list[str] = []
    cursor = 0
    for category, start, end in resolved:
        parts.append(text[cursor:start])
        parts.append(f"[{category.upper()}_REDACTED]")
        counts[category] = counts.get(category, 0) + 1
        cursor = end
    parts.append(text[cursor:])

    return ScanResult(
        redacted_text="".join(parts),
        category_counts=counts,
        raw_char_count=len(text),
    )
