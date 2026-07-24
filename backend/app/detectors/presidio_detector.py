from presidio_analyzer import AnalyzerEngine

# Deliberately restricted to entity types the regex layer cannot cover
# (unstructured NLP/NER detection: names, locations, special-category
# signals). Presidio's own EMAIL_ADDRESS/PHONE_NUMBER/CREDIT_CARD/IP_ADDRESS
# recognizers are excluded so the two detectors don't compete over the same
# spans — regex owns structured/deterministic formats (including UK-specific
# ones Presidio has no notion of, like NI numbers), Presidio owns everything
# that needs language understanding. Confirmed during standalone testing that
# without this restriction, Presidio's PHONE_NUMBER recognizer misfires on
# UK_NHS-shaped numbers.
PRESIDIO_ENTITIES = [
    "PERSON",
    "LOCATION",
    "NRP",
    "MEDICAL_LICENSE",
    "UK_NHS",
    "US_SSN",
    "IBAN_CODE",
    "CRYPTO",
]

MIN_CONFIDENCE = 0.4

_analyzer: AnalyzerEngine | None = None


def get_analyzer() -> AnalyzerEngine:
    global _analyzer
    if _analyzer is None:
        _analyzer = AnalyzerEngine()
    return _analyzer


def analyze(text: str) -> list[tuple[str, int, int, float]]:
    """Returns (category, start, end, confidence) tuples, category lowercased
    to match the regex detectors' naming convention."""
    results = get_analyzer().analyze(text=text, language="en", entities=PRESIDIO_ENTITIES)
    return [
        (r.entity_type.lower(), r.start, r.end, r.score)
        for r in results
        if r.score >= MIN_CONFIDENCE
    ]
