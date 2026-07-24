from dataclasses import dataclass

from .detectors.combined import Match
from .policy import policy

# Severity weight per category, out of 100 in isolation. Regex categories are
# structured/deterministic (confidence always 1.0); Presidio categories are
# NLP/NER-based and their contribution is scaled by Presidio's own confidence
# score for that match.
CATEGORY_WEIGHTS: dict[str, float] = {
    # regex-sourced
    "aws_key": 35,
    "credit_card": 30,
    "ni_number": 30,
    "token_url": 25,
    "uk_phone": 15,
    "email": 10,
    "ip_address": 8,
    # presidio-sourced
    "medical_license": 30,
    "uk_nhs": 30,
    "us_ssn": 30,
    "iban_code": 30,
    "crypto": 20,
    "nrp": 25,
    "person": 15,
    "location": 10,
}

MAX_COUNTED_MATCHES_PER_CATEGORY = 3

# Phrases suggesting the author already believes the content is sensitive.
# Deliberately capped low relative to actual PII detections — context alone
# shouldn't be able to push a prompt past "medium" on its own.
CONTEXTUAL_KEYWORDS: dict[str, float] = {
    "confidential": 15,
    "strictly private": 15,
    "internal use only": 15,
    "do not share": 15,
    "do not distribute": 15,
    "proprietary": 10,
    "trade secret": 20,
    "under nda": 20,
}
MAX_CONTEXTUAL_SCORE = 40.0


@dataclass
class RiskResult:
    regex_score: float
    presidio_score: float
    contextual_score: float
    combined_score: float
    risk_level: str


def score_contextual(text: str) -> tuple[float, list[str]]:
    lowered = text.lower()
    matched = [phrase for phrase in CONTEXTUAL_KEYWORDS if phrase in lowered]
    total = sum(CONTEXTUAL_KEYWORDS[phrase] for phrase in matched)
    return min(MAX_CONTEXTUAL_SCORE, total), matched


def level_for_score(score: float) -> str:
    t = policy.thresholds
    if score >= t.critical:
        return "critical"
    if score >= t.high:
        return "high"
    if score >= t.medium:
        return "medium"
    return "low"


def score_from_matches(matches: list[Match], text: str) -> RiskResult:
    regex_total = 0.0
    presidio_total = 0.0
    counted_by_category: dict[str, int] = {}

    for m in matches:
        counted = counted_by_category.get(m.category, 0)
        if counted >= MAX_COUNTED_MATCHES_PER_CATEGORY:
            continue
        counted_by_category[m.category] = counted + 1

        weight = CATEGORY_WEIGHTS.get(m.category, 5)
        contribution = weight * m.confidence
        if m.source == "regex":
            regex_total += contribution
        else:
            presidio_total += contribution

    contextual_score, _ = score_contextual(text)

    # regex_score/presidio_score are clamped independently for reporting
    # (matches the Phase 1 semantics of "0-100 severity from this detector
    # alone"); combined_score is computed from the true unclamped totals so
    # two moderate detectors can still add up to a high combined severity.
    regex_score = min(100.0, regex_total)
    presidio_score = min(100.0, presidio_total)
    combined_score = min(100.0, regex_total + presidio_total + contextual_score)

    return RiskResult(
        regex_score=regex_score,
        presidio_score=presidio_score,
        contextual_score=contextual_score,
        combined_score=combined_score,
        risk_level=level_for_score(combined_score),
    )
