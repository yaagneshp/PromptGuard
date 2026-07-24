from dataclasses import dataclass, field

from . import presidio_detector
from .regex_detectors import find_regex_matches


@dataclass
class Match:
    category: str
    start: int
    end: int
    source: str  # "regex" | "presidio"
    confidence: float = 1.0


@dataclass
class CombinedScanResult:
    redacted_text: str
    raw_char_count: int
    matches: list[Match] = field(default_factory=list)


def scan_text_combined(text: str) -> CombinedScanResult:
    """Runs regex and Presidio over the same raw text, resolves overlaps
    across both, and redacts in a single pass.

    Regex and Presidio are scoped to disjoint entity universes (see
    presidio_detector.PRESIDIO_ENTITIES), so overlaps between the two are
    expected to be rare — but matches are still resolved as one combined,
    globally-ordered list rather than two independent passes, so a
    pathological overlap can't produce double-redaction artifacts.
    """
    all_matches: list[Match] = [
        Match(category=category, start=start, end=end, source="regex", confidence=1.0)
        for category, start, end in find_regex_matches(text)
    ]
    all_matches += [
        Match(category=category, start=start, end=end, source="presidio", confidence=confidence)
        for category, start, end, confidence in presidio_detector.analyze(text)
    ]

    # Earliest start wins; ties broken by longest match, then regex over presidio
    all_matches.sort(key=lambda m: (m.start, -(m.end - m.start), 0 if m.source == "regex" else 1))
    resolved: list[Match] = []
    last_end = -1
    for m in all_matches:
        if m.start >= last_end:
            resolved.append(m)
            last_end = m.end

    parts: list[str] = []
    cursor = 0
    for m in sorted(resolved, key=lambda m: m.start):
        parts.append(text[cursor:m.start])
        parts.append(f"[{m.category.upper()}_REDACTED]")
        cursor = m.end
    parts.append(text[cursor:])

    return CombinedScanResult(redacted_text="".join(parts), raw_char_count=len(text), matches=resolved)
