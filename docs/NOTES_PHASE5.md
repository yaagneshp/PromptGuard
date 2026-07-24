# Implementation Notes — Phase 5: Dataset, Testing & Evaluation

## Dataset

[dataset/generate_dataset.py](../dataset/generate_dataset.py) produces
[dataset/prompts.jsonl](../dataset/prompts.jsonl): 368 labeled synthetic
prompts (108 benign, 160 confidential, 100 policy-violating), each with
ground-truth `expected_categories` and `expected_policy_violation`. This
came out somewhat larger than the "150-300, modest" scope agreed earlier —
acceptable since generation and evaluation are both local and fast (no API
costs, no manual labeling time), so the extra statistical power was free.

**Every PII-shaped value is a well-known, officially reserved, or
industry-standard placeholder — never anything that could identify a real
person:**

| Category | Source of the synthetic value |
|---|---|
| Email | `example.com`/`example.co.uk` (reserved for documentation, RFC 2606) |
| UK phone | Ofcom's ranges reserved for fiction/drama use (07700 900xxx, 020 7946 0xxx) |
| IP address | RFC 5737 TEST-NET ranges (192.0.2.0/24, 198.51.100.0/24, 203.0.113.0/24) |
| Credit card | Industry-standard test numbers from payment processors' own docs |
| AWS key | AWS's own published non-functional example (`AKIAIOSFODNN7EXAMPLE`) |
| NI number | Constructed per HMRC's published format rules (see bug below) |
| NHS number | A synthetic number confirmed against Presidio's checksum in Phase 3 |
| IBAN | The standard Wikipedia/documentation example IBAN |
| US SSN | Constructed in the 900-999 area-number range the SSA has never issued |
| Crypto address | The Bitcoin genesis-block address — public, owned by no one |
| Names | Generic placeholders (John Smith, Jane Doe, Sarah Connor, etc.) |

## Two bugs caught during evaluation (in the dataset, not the detectors)

**NI number letters.** Two of three synthetic NI numbers
(`CD654321A`, `EF112233D`) used letter combinations HMRC's own rules
prohibit (`D` and `F` are invalid as the second letter) — the *exact* same
mistake as the `QQ` NI number I used in Phase 1 curl testing. The regex
correctly rejected them; the dataset was wrong, not the detector. This
initially showed up as `ni_number` recall of 0.35 (7/20) — investigating
*why* a supposedly-deterministic regex category had imperfect recall is
what surfaced it. Fixed by replacing both with rule-compliant values
(`JM772311B`, `SN458213A`) and re-verifying against the compiled regex
directly before regenerating.

**Medical license format.** Presidio's `MEDICAL_LICENSE` recognizer never
fired on either synthetic value tried (`MD123456`, `GMC7654321`) — a
standalone check showed Presidio instead classifies these as
`US_DRIVER_LICENSE` (excluded from our `PRESIDIO_ENTITIES` scope), meaning
its actual expected format wasn't reverse-engineered from the two guesses
tried. Rather than keep guessing under time pressure, the dataset now
tests `person` detection only for these prompts, with the gap documented
here and in `generate_dataset.py`. `medical_license` remains enabled in the
live pipeline in case real-world text does match Presidio's actual pattern
— it simply has zero test coverage in this evaluation.

Both are worth a sentence in the dissertation's methodology section: they
demonstrate that investigating a suspiciously low metric, rather than
reporting it uncritically, is what surfaces dataset bugs versus genuine
detector limitations.

## Evaluation methodology

Three complementary views, all in [evaluate.py](../dataset/evaluate.py),
each baseline (regex-only, i.e. what Phase 1 shipped) vs hybrid (regex +
Presidio + contextual, i.e. Phase 3):

1. **Per-category detection** (micro-averaged precision/recall/F1 across
   all 14 categories) — the finest-grained view of raw detection capability.
2. **Prompt-level, any PII detected at all** — coarser: did the system flag
   *anything* in a prompt that should have something flagged? Isolates
   detection capability from the risk-scoring policy.
3. **Prompt-level, flagged at the medium-risk threshold (≥25)** — the
   *operational* view: did the system actually raise an alert? Deliberately
   answers a different question from (2) — see discussion below.

## Results

Full tables/charts in [dataset/results/](../dataset/results/)
(`summary.md`, `chart_*.png`).

| | Baseline | Hybrid |
|---|---|---|
| Per-category F1 (micro) | 0.667 | 0.940 |
| Prompt-level F1 (any detection) | 0.738 | 0.970 |
| Prompt-level F1 (risk-threshold) | 0.434 | 0.610 |
| Mean scan latency | 0.07 ms | 15.5 ms |

**The headline finding:** hybrid detection roughly triples per-category
recall (0.50 → 0.98) at the cost of a small precision drop (1.0 → 0.90) and
a 10% false-positive rate at the prompt level (0% → 10.2%) — a favorable
trade given the baseline was *structurally* incapable of detecting names,
locations, or several special-category signals at all (zero recall on those
categories by construction, not by imperfect tuning).

**Why risk-threshold recall (0.44) looks much lower than any-detection
recall (0.98), and why that's not a detection failure:** the ≥25 threshold
requires *accumulated* severity before flagging — a single email (weight 10)
or a single location (weight 10) correctly doesn't clear it alone, by
design, to avoid alert fatigue on low-severity single mentions. Many
"confidential"-labeled prompts in the dataset contain exactly one low-weight
category, so they're correctly detected (any-detection view) but correctly
*not* escalated to an alert (threshold view). These are two different
questions — "can the system see the PII" vs "should this specific prompt
page someone" — and the large gap between them is really a statement about
threshold calibration, not a detection gap. A natural piece of future work
is sweeping the threshold and plotting a precision-recall curve to justify
the specific cutoff chosen, rather than asserting policy.yaml's default is
correct.

**False-positive analysis (the 11 prompt-level FPs, all from `location`):**
inspecting them directly showed Presidio correctly identifying "Rome" and
"Egypt" as LOCATION entities in prompts like *"Write a poem about the
history of Rome"* — genuinely a place name, but not personal data in this
context, since it isn't tied to an identifiable individual. This is a real,
known limitation of NER-based detection: it operates on entity type, not on
"is this location bound to a person" discourse-level understanding. Not
fixed by hacking the detector (that would just re-introduce false
negatives for the cases where location *does* matter, e.g. "my colleague
lives in Manchester") — documented instead as a limitation, with a concrete
future-work direction: weight LOCATION lower unless a PERSON entity
co-occurs nearby.

**Latency:** the hybrid pipeline is ~230x slower per scan (15.5ms vs
0.07ms mean) — the spaCy NER inference cost. Still fast in absolute terms
for a background extension use case (sub-20ms even at P95), but a real
trade-off worth stating plainly rather than hiding: the hybrid approach
buys detection quality at a measurable (if small in absolute terms)
latency cost.

## What's still outstanding before feature freeze

Two items from the original Phase 5 plan couldn't be completed without
your involvement, same limitation as Phase 2:

- **"Run full end-to-end tests across all 8 platforms, fix integration
  bugs"** — still requires loading the unpacked extension in your own
  logged-in Chrome and testing against the real ChatGPT/Claude/Gemini/
  Copilot/Perplexity/DeepSeek/Grok/Mistral UIs. Everything testable without
  your login (capture-engine logic, backend integration, detection
  pipeline, dashboard) has been verified; the real-DOM pass is the one
  remaining gap.
- **Extension CPU/memory profiling** — requires Chrome's own task manager
  or a profiler attached to your real browser session; not something
  reachable from this side.

Once you've done the real-platform pass, this is a reasonable point for
the "feature freeze - bug fixes only" the original plan calls for.
