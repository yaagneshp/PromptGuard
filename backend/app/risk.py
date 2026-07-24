from dataclasses import dataclass

# Severity weight per PII category, out of 100. Tuned for MVP; revisit once
# Presidio + contextual scoring are wired in during Phase 3.
CATEGORY_WEIGHTS: dict[str, float] = {
    "aws_key": 35,
    "credit_card": 30,
    "ni_number": 30,
    "token_url": 25,
    "uk_phone": 15,
    "email": 10,
    "ip_address": 8,
}

# Extra matches of the same category still add signal, but with diminishing
# returns — cap how many times a category's weight counts.
MAX_COUNTED_MATCHES_PER_CATEGORY = 3

RISK_THRESHOLDS = [
    (75, "critical"),
    (50, "high"),
    (25, "medium"),
    (0, "low"),
]


@dataclass
class RiskResult:
    regex_score: float
    combined_score: float
    risk_level: str


def score_from_counts(category_counts: dict[str, int]) -> RiskResult:
    total = 0.0
    for category, count in category_counts.items():
        weight = CATEGORY_WEIGHTS.get(category, 5)
        total += weight * min(count, MAX_COUNTED_MATCHES_PER_CATEGORY)

    regex_score = min(100.0, total)
    # Phase 1: combined score is regex-only. Phase 3 folds in Presidio and
    # contextual keyword signals here.
    combined_score = regex_score

    risk_level = "low"
    for threshold, label in RISK_THRESHOLDS:
        if combined_score >= threshold:
            risk_level = label
            break

    return RiskResult(regex_score=regex_score, combined_score=combined_score, risk_level=risk_level)
