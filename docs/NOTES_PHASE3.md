# Implementation Notes — Phase 3: Hybrid Risk Engine + Compliance

## Presidio standalone test

Before touching the backend, ran `backend/tests/test_presidio_standalone.py`
against sample text. Confirmed:
- `PERSON` and `LOCATION` detected correctly with 0.85 confidence (spaCy NER
  via `en_core_web_lg`).
- `UK_NHS` detected at 1.00 confidence — Presidio ships a dedicated UK NHS
  number recognizer.
- Importantly, Presidio's own `PHONE_NUMBER` recognizer **misfired on the same
  NHS number** (`943 476 5919` matched both `UK_NHS` and `PHONE_NUMBER`).
  This directly justified restricting which Presidio entities the app
  actually uses (see below) — letting regex and Presidio both freely detect
  phone-number-shaped strings would produce inconsistent, conflicting labels
  for the same span.

## Division of labour: regex vs. Presidio

`app/detectors/presidio_detector.py` restricts Presidio's `entities=` list to
`PERSON, LOCATION, NRP, MEDICAL_LICENSE, UK_NHS, US_SSN, IBAN_CODE, CRYPTO` —
deliberately excluding Presidio's built-in `EMAIL_ADDRESS`, `PHONE_NUMBER`,
`CREDIT_CARD`, `IP_ADDRESS` recognizers. Rationale:

- Regex owns everything **structured and deterministic**, including
  UK-specific formats Presidio has no notion of (NI numbers) and things a
  Luhn checksum can validate exactly (credit cards) — regex is either right
  or wrong, no confidence score needed.
- Presidio owns everything that needs **language understanding** — you
  cannot regex a person's name or a place. This is the actual value-add of
  going "hybrid": regex alone can never catch "my colleague Sarah Connor",
  only an NER model can.
- Keeping the two detectors' entity universes disjoint means overlap
  resolution across sources is a rare edge case, not the common case — the
  combined scanner ([combined.py](../backend/app/detectors/combined.py))
  still resolves overlaps defensively (regex wins ties), but it's a safety
  net, not load-bearing.

## Hybrid risk scoring

[risk.py](../backend/app/risk.py) computes three independent sub-scores, all
0–100:
- `regex_score` — weighted sum of regex-detected categories (unchanged from
  Phase 1, weights: aws_key 35, credit_card/ni_number 30, token_url 25,
  uk_phone 15, email 10, ip_address 8).
- `presidio_score` — weighted sum of Presidio-detected categories, each
  contribution scaled by Presidio's own confidence score for that match
  (weight × confidence). Weights: medical_license/uk_nhs/us_ssn/iban_code 30,
  nrp 25, crypto 20, person 15, location 10.
- `contextual_score` — a small fixed-phrase keyword list ("confidential",
  "under nda", "do not share", etc.), capped at 40 points total so context
  alone can never push a prompt past "medium" — it can only push an
  already-flagged prompt higher.

`combined_score = min(100, regex_total + presidio_total + contextual_score)`
using the **unclamped** per-source totals (not the individually-clamped
`regex_score`/`presidio_score` display values), so e.g. a name (presidio) plus
an NI number (regex) genuinely stack rather than each being capped at 100
independently first. Both sub-scores are still clamped to 100 individually
for reporting, matching the Phase 1 schema semantics of "0–100 severity from
this detector alone."

Risk level thresholds (medium/high/critical) now come from `policy.yaml`
rather than being hardcoded, so an org can tune sensitivity without a code
change.

## Policy config

[policy.yaml](../backend/policy.yaml) / [policy.py](../backend/app/policy.py):
- `thresholds` — risk level cutoffs (medium/high/critical).
- `blocked_categories` — categories that mark an event as a policy violation
  regardless of overall score (currently: aws_key, credit_card, ni_number,
  us_ssn, iban_code, uk_nhs, crypto — i.e. hard financial/credential/health
  identifiers, on the view that even one instance is a compliance concern
  independent of how "risky" the rest of the prompt reads).
- `allowed_platforms` — if non-empty, any platform not in the list is itself
  a policy violation, independent of prompt content (verified: a prompt with
  zero PII sent to `"some_random_llm"` still comes back
  `policy_violation: true`).

`RiskScore.policy_violation` (new column) is `True` if either condition
holds. This required wiping the local dev SQLite file and letting
`create_all` rebuild it — acceptable since it only held test data from
earlier curl runs, never committed (`.db` is gitignored).

## GDPR compliance tagging

[gdpr.py](../backend/app/gdpr.py) maps each detected category to one or more
UK GDPR articles with a short rationale, stored in a new `compliance_tags`
table (one row per event/category/article combination). **This is explicitly
documented in the module docstring as an illustrative mapping for the
tool's reporting output, not legal advice** — worth repeating verbatim in the
dissertation, since claiming otherwise would overstate what a keyword-mapping
table can responsibly assert. Special-category signals (`nrp`,
`medical_license`, `uk_nhs`) are tagged Art. 9; direct identifiers get Art.
4(1); credential/security-relevant categories (`aws_key`, `token_url`) get
Art. 32 rather than a personal-data article, since a leaked AWS key isn't
itself personal data but is squarely a "security of processing" concern.

## Testing performed

All via curl against the live server (backend restarted with a fresh DB to
pick up the schema changes):
- Presidio-only prompt (name + location, no regex-detectable PII) →
  `presidio_score: 21.25` (15×0.85 + 10×0.85), correct GDPR tags, `low` risk.
- Blocked-category prompt (credit card) → `policy_violation: true`,
  `risk_level: medium` (30 alone doesn't reach "high" — violation and risk
  level are independent signals, by design).
- Contextual boost: a name+location prompt (21.25) plus "confidential" +
  "do not share" (+15 +15 = 30) → `combined_score: 51.25`, `risk_level: high`
  — confirms context can escalate a moderate finding but the earlier
  Presidio-only test (0 context, same entities) stayed `low`/`medium`-range,
  showing context isn't inflating scores unconditionally.
- Disallowed-platform prompt ("some_random_llm", zero PII) →
  `policy_violation: true` with `risk_level: low` — confirms platform policy
  is tracked independently of content risk.
- Mixed regex+Presidio prompt (NHS number + patient name) → both detected,
  correct GDPR tags for each. Also surfaced a genuine NER boundary
  imprecision: spaCy's PERSON span over-extended to swallow the adjacent word
  "NHS" (`"Jane Doe NHS"` tagged as one PERSON entity). Not a bug in our
  code — an inherent NER limitation worth citing in the evaluation chapter's
  discussion of false-positive/boundary-error modes.
- Re-ran the Phase 2 extension integration test (`background.test.js`)
  against the upgraded backend — still passes unchanged, confirming the
  additive schema changes (new `policy_violation` field, new
  `compliance_tags` list) don't break the existing extension contract.

## Known limitations / future work

- `contextual_score`'s keyword list is small and English-only; a real
  deployment would want this configurable per-org alongside the policy YAML.
- GDPR article mapping is a flat category→article table with no way to
  express "Art. 9 only applies if combined with a health-related category" —
  fine for an MVP illustrative feature, not a substitute for real legal
  categorisation logic.
- Presidio's NER entity boundaries are occasionally imprecise (see NHS number
  example above) — worth quantifying in Phase 5's precision/recall
  evaluation rather than treating as fully solved.
