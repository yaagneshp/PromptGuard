"""Standalone smoke test for Presidio, run directly (not via pytest) to
confirm the analyzer loads and produces sensible entities before wiring it
into the app. Run with: venv/Scripts/python tests/test_presidio_standalone.py
"""

from presidio_analyzer import AnalyzerEngine

analyzer = AnalyzerEngine()

SAMPLES = [
    "My name is John Smith and I live in Manchester, please draft a letter.",
    "Can you summarise this for Sarah Connor who works at Cyberdyne Systems in London?",
    "Just write me a poem about the ocean, nothing personal here.",
    "Patient Jane Doe's NHS number is 943 476 5919, please check the record.",
]

for text in SAMPLES:
    print(f"\n--- {text!r}")
    results = analyzer.analyze(text=text, language="en")
    for r in results:
        span = text[r.start:r.end]
        print(f"  {r.entity_type:20s} score={r.score:.2f}  {span!r}")
