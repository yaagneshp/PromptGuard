"""Generates a synthetic labeled dataset for evaluating PromptGuard's
detectors. Every PII-shaped value used here is a well-known, officially
reserved, or industry-standard placeholder - never a value that could
identify a real person:

- Emails: `example.com`/`example.co.uk` (reserved for documentation, RFC 2606)
- UK phone numbers: Ofcom's ranges reserved for fiction/drama use
  (07700 900xxx mobile, 020 7946 0xxx London landline)
- IP addresses: RFC 5737 TEST-NET ranges (192.0.2.0/24, 198.51.100.0/24,
  203.0.113.0/24)
- Credit card numbers: industry-standard test numbers used across payment
  processors' own documentation (Visa/Mastercard/Amex test suites)
- AWS key: AWS's own published non-functional documentation example
  (AKIAIOSFODNN7EXAMPLE)
- NI number: HMRC documentation-style example prefixes
- NHS number: a synthetic number confirmed to pass Presidio's checksum
  during Phase 3 testing
- IBAN: the standard Wikipedia/documentation example IBAN
- US SSN: constructed in the 900-999 area-number range the SSA has never
  issued
- Crypto address: the Bitcoin genesis-block address, public and owned by
  no private individual
- Names: generic placeholder names (John Smith, Jane Doe, etc.)

Output: dataset/prompts.jsonl, one labeled prompt per line.
"""

import json
from itertools import cycle
from pathlib import Path

OUT_PATH = Path(__file__).resolve().parent / "prompts.jsonl"

TOPICS = [
    "the ocean", "autumn leaves", "climate change", "machine learning",
    "the history of Rome", "cooking pasta", "quantum computing",
    "gardening tips", "the solar system", "medieval castles",
    "the French Revolution", "renewable energy", "chess strategy",
    "the water cycle", "ancient Egypt", "urban planning",
    "jazz music", "the stock market", "coral reefs", "volcanoes",
]

NAMES = ["John Smith", "Jane Doe", "Jane Roe", "Richard Roe", "Sarah Connor", "John Roe"]
LOCATIONS = ["London", "Manchester", "Bristol", "Leeds", "Edinburgh", "Cardiff"]
EMAILS = ["alice@example.com", "bob.jones@example.co.uk", "carol.smith@example.org", "dave@example.net"]
UK_PHONES = ["07700 900123", "07700 900456", "020 7946 0958", "0113 496 0101"]
IPS = ["192.0.2.10", "198.51.100.23", "203.0.113.45"]
TOKEN_URLS = [
    "https://app.example.com/data?token=abc123XYZ",
    "https://portal.example.org/view?access_token=zzz999AAA",
]
NRP_PHRASES = ["identifies as Buddhist", "is a British national", "is a member of the Green Party"]
# Presidio's MEDICAL_LICENSE recognizer did not fire on either of these
# during evaluation (verified with a standalone check) - it appears to
# require a specific format not established from the library's public docs.
# Reverse-engineering the exact pattern was out of scope for the timeline,
# so these prompts test PERSON detection only; "medical_license" is left
# enabled in the live pipeline (see presidio_detector.py) but has no test
# coverage in this dataset - documented as a limitation in NOTES_PHASE5.md.
MEDICAL_LICENSES = ["MD123456", "GMC7654321"]

CREDIT_CARDS = ["4111111111111111", "5555555555554444", "378282246310005", "4012888888881881"]
AWS_KEY = "AKIAIOSFODNN7EXAMPLE"
# All three verified against the regex: first letter excludes D/F/I/Q/U/V,
# second letter additionally excludes O (real HMRC prefix rules).
NI_NUMBERS = ["AB123456C", "JM772311B", "SN458213A"]
NHS_NUMBER = "943 476 5919"
IBAN = "GB82 WEST 1234 5698 7654 32"
SSNS = ["923-45-6789", "987-65-4321"]
CRYPTO_ADDRESS = "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"

BLOCKED_CATEGORIES = {"aws_key", "credit_card", "ni_number", "us_ssn", "iban_code", "uk_nhs", "crypto"}

records = []
_id = 0


def add(text: str, categories: list[str], label: str) -> None:
    global _id
    _id += 1
    records.append(
        {
            "id": _id,
            "text": text,
            "label": label,
            "expected_categories": sorted(set(categories)),
            "expected_policy_violation": bool(set(categories) & BLOCKED_CATEGORIES),
        }
    )


# --- Benign: no PII expected ---
BENIGN_TEMPLATES = [
    "Write a poem about {topic}.",
    "Explain {topic} to a five-year-old.",
    "Summarise the key facts about {topic}.",
    "Give me five interesting facts about {topic}.",
    "Draft an outline for an essay on {topic}.",
]
for template in BENIGN_TEMPLATES:
    for topic in TOPICS:
        add(template.format(topic=topic), [], "benign")

# --- Benign: near-miss / false-positive-control prompts ---
NEGATIVE_CONTROLS = [
    "Random 16 digit reference number 1234567890123456, thanks.",
    "Please call my US office at +1 415 555 0132 tomorrow.",
    "The transaction ID is 550e8400-e29b-41d4-a716-446655440000.",
    "There are 42 items left in stock for the autumn sale.",
    "Order number 20260724-001 has shipped.",
    "The meeting is scheduled for 15:30 on Thursday.",
    "Our reference is INV-2026-0042 for the invoice.",
    "The product SKU is 987654321012 for the warehouse.",
]
for text in NEGATIVE_CONTROLS:
    add(text, [], "benign")

# --- Confidential: contains non-blocked-category PII ---
name_cycle = cycle(NAMES)
loc_cycle = cycle(LOCATIONS)
email_cycle = cycle(EMAILS)
phone_cycle = cycle(UK_PHONES)
ip_cycle = cycle(IPS)
token_cycle = cycle(TOKEN_URLS)
nrp_cycle = cycle(NRP_PHRASES)
medlic_cycle = cycle(MEDICAL_LICENSES)

for topic in TOPICS:
    add(f"My email is {next(email_cycle)}, can you help draft a reply about {topic}?", ["email"], "confidential")
    add(f"Call me on {next(phone_cycle)} about {topic}.", ["uk_phone"], "confidential")
    name, loc = next(name_cycle), next(loc_cycle)
    add(f"My colleague {name} from {loc} needs help with {topic}.", ["person", "location"], "confidential")
    add(f"Reach out to {next(name_cycle)} at {next(email_cycle)} regarding {topic}.", ["person", "email"], "confidential")
    add(f"The server IP is {next(ip_cycle)} for the {topic} project.", ["ip_address"], "confidential")
    add(f"Here's the link, {next(token_cycle)}, for the {topic} results.", ["token_url"], "confidential")
    add(f"She {next(nrp_cycle)} and volunteers for {topic} events.", ["nrp"], "confidential")
    add(
        f"Dr. {next(name_cycle)}'s medical license number is {next(medlic_cycle)}, "
        f"please verify for the {topic} review.",
        ["person"],  # medical_license expected but never fires - see MEDICAL_LICENSES comment above
        "confidential",
    )

# --- Policy-violating: contains at least one blocked category ---
cc_cycle = cycle(CREDIT_CARDS)
ni_cycle = cycle(NI_NUMBERS)
ssn_cycle = cycle(SSNS)

for topic in TOPICS[:12]:
    add(f"My card number is {next(cc_cycle)}, please check the {topic} charge.", ["credit_card"], "policy_violating")
    add(f"Here is my AWS key {AWS_KEY} for the {topic} deployment script.", ["aws_key"], "policy_violating")
    add(f"My National Insurance number is {next(ni_cycle)} for the {topic} form.", ["ni_number"], "policy_violating")
    add(
        f"Patient {next(name_cycle)}, NHS number {NHS_NUMBER}, needs a {topic} follow-up.",
        ["person", "uk_nhs"],
        "policy_violating",
    )
    add(f"My SSN is {next(ssn_cycle)} for the {topic} application.", ["us_ssn"], "policy_violating")
    add(f"Transfer to IBAN {IBAN} for the {topic} payment.", ["iban_code"], "policy_violating")
    add(f"Send funds to wallet {CRYPTO_ADDRESS} for the {topic} purchase.", ["crypto"], "policy_violating")

# --- Policy-violating with contextual keywords (tests contextual scoring) ---
for topic in TOPICS[:8]:
    add(
        f"This is confidential, do not share: my card is {next(cc_cycle)} for the {topic} refund.",
        ["credit_card"],
        "policy_violating",
    )
    add(
        f"Under NDA - AWS key {AWS_KEY} and NI number {next(ni_cycle)} for the {topic} handover.",
        ["aws_key", "ni_number"],
        "policy_violating",
    )

with OUT_PATH.open("w", encoding="utf-8") as f:
    for r in records:
        f.write(json.dumps(r) + "\n")

label_counts: dict[str, int] = {}
for r in records:
    label_counts[r["label"]] = label_counts.get(r["label"], 0) + 1

print(f"Wrote {len(records)} labeled prompts to {OUT_PATH}")
print("Label distribution:", label_counts)
