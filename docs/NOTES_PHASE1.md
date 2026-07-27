# Implementation Notes — Phase 1: Backend Foundation

## Overview

PromptGuard's backend is a FastAPI service that ingests telemetry events (prompt
submissions to LLM platforms), scans them for PII using regex detectors, computes
a risk score, and persists only a redacted version of the text.

Stack: FastAPI, SQLAlchemy 2.0 (declarative `Mapped`/`mapped_column` style), SQLite,
Pydantic v2 / pydantic-settings for config.

## Architecture decisions

**Single-user MVP auth.** One static API key (`X-API-Key` header, checked via a
FastAPI dependency in [auth.py](../backend/app/auth.py)) gates both the ingestion
endpoint and the read endpoint. This matches the project's single-user/local-demo
deployment scope — no login system, no per-user API keys. If multi-tenant auth is
needed later, `require_api_key` is the single seam to replace.

**`users` table ≠ login accounts.** The `users` table represents *data subjects*
(the org employees whose prompts are being monitored), identified by a
pseudonymous `external_user_id` supplied by the extension — not people who log
into the dashboard. This reconciles "single API key for MVP" with the Phase 4
requirement for per-user usage breakdowns: there's exactly one system credential,
but many monitored users can appear in the data.

**No raw text is ever persisted.** This was the most important architectural
decision and is worth a paragraph in the dissertation's data-protection/ethics
section. The ingestion flow is:

1. Raw prompt text arrives in the request body.
2. `scan_text()` runs regex detectors over it in memory and produces a
   `redacted_text` string (PII spans replaced with `[CATEGORY_REDACTED]` tokens)
   plus per-category match counts.
3. Only `redacted_text`, the match counts, and a SHA-256 hash of the *original*
   text (`raw_text_hash`) are written to the database. The raw string is never
   passed to the ORM layer and goes out of scope once the request handler
   returns.
4. `raw_text_hash` exists purely for integrity/dedup auditing — it is one-way and
   cannot be reversed to recover the original text.

This was chosen over storing raw text (simpler, but makes the tool itself a PII
liability) and over a fully configurable per-policy retention model (more
realistic for enterprise DLP, but too much scope for the timeline). It's a
legitimate "future work" line: policy-driven retention tiers.

## Database schema

| Table | Purpose |
|---|---|
| `users` | Pseudonymous data subjects (not login accounts) |
| `platforms` | LLM platforms (chatgpt, claude, gemini, copilot, perplexity, deepseek, grok, mistral), created lazily on first event |
| `events` | One row per captured prompt submission: redacted text, char count, raw-text hash, client/server timestamps |
| `detections` | One row per PII category matched in an event (category + count + detector source — no matched substrings stored) |
| `risk_scores` | One-to-one with `events`. Has `regex_score` (populated now), `presidio_score` and `contextual_score` (nullable, wired up in Phase 3), `combined_score`, `risk_level` |

`platforms` and `users` are get-or-create on ingestion, so the extension never
needs a separate registration step — it just sends events.

## PII detectors (regex, Phase 1 scope)

Implemented in [regex_detectors.py](../backend/app/detectors/regex_detectors.py):
email, UK phone number, UK National Insurance number, credit card (regex
candidate + Luhn checksum validation), AWS access key ID, IPv4 address,
token-bearing URL (query string containing `token=`, `api_key=`,
`access_token=`, `secret=`, `auth=`, or `session=`).

Each detector is `(category, compiled_pattern, optional_validator)`. `scan_text()`
runs all patterns, resolves overlapping matches (earliest start wins, ties broken
by longest match), and builds the redacted string in a single left-to-right pass.

**Bugs caught during curl testing, worth citing as evidence of a testing
methodology:**
- Both the UK phone and credit card regexes originally allowed a trailing
  optional separator (`\s?` / `[ -]?`) inside the repeated match group. Since a
  regex `\b` word boundary is satisfied at a space→letter transition too, the
  match silently swallowed the space after the number (`"123456 or"` →
  `"[UK_PHONE_REDACTED]or"`). Fixed by restructuring both patterns as
  `first_digit(?:separator?digit){n}` so the separator can only appear *between*
  digits, never trailing.
- NI number test data initially used `QQ` as a placeholder prefix, which is
  correctly rejected — `Q` is one of the letters HMRC prohibits in either
  position of a real NI number. This wasn't a detector bug; it validated that
  the character-class exclusions (`D,F,I,Q,U,V` first letter; `D,F,I,O,Q,U,V`
  second letter) work as intended. Re-tested with a valid prefix (`AB`).

## Risk scoring (regex-only baseline)

[risk.py](../backend/app/risk.py) assigns a per-category severity weight (e.g.
AWS key 35, credit card/NI 30, token URL 25, phone 15, email 10, IP 8), sums
weighted counts (capped at 3 counted matches per category to avoid one repeated
low-severity category dominating the score), and maps the total to a 0–100
`regex_score`. Thresholds: ≥75 critical, ≥50 high, ≥25 medium, else low.

`combined_score` currently just equals `regex_score` — the field exists now so
Phase 3 can fold in Presidio and contextual-keyword signals without a schema or
API change.

## Testing performed

All tests run via `curl` against a live local uvicorn instance (no
Postman collection built yet — curl was faster for this pass, Postman collection
can be exported later for the dissertation appendix if useful):

- 401 on missing/incorrect API key for both `POST /events/ingest` and `GET /events`.
- Benign text → zero detections, `risk_level: low`.
- Each of the 7 PII categories individually → correct detection, correct
  redaction placeholder, correct category in `detections`.
- Invalid credit-card-shaped number (fails Luhn) → correctly *not* flagged.
- Combined payload (email + NI number + AWS key in one prompt) → all three
  detected, `combined_score: 75`, `risk_level: critical`.
- `GET /events?limit=N` → returns events newest-first, respects `limit`.
- Verified directly against the SQLite schema (`sqlite_master`) that no column
  anywhere stores raw prompt text — only `redacted_text` and `raw_text_hash`.

## Known limitations / future work

- UK phone regex is deliberately recall-oriented (accepts any `0`/`+44` prefix
  followed by the right digit count) — will over-match some non-phone
  11-digit-with-spaces sequences. Acceptable for MVP; Presidio in Phase 3 should
  help cross-check.
- IP address detector doesn't distinguish private/loopback ranges
  (192.168.x.x, 127.0.0.1) from public IPs — currently flagged at flat weight 8.
  Could be split into separate categories with different severity later.
- No policy config yet (thresholds/blocked categories/allowed platforms are
  hardcoded) — planned for Phase 3.
- No rate limiting or request size limits on `/events/ingest` yet.
