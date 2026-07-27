# PromptGuard

MSc dissertation project. A Chrome extension + backend + dashboard for detecting sensitive/PII content
in prompts submitted to LLM chat platforms (ChatGPT, Claude, Gemini, Copilot,
Perplexity, DeepSeek, Grok, Mistral Le Chat), scoring the risk, tagging it
against UK GDPR articles, and surfacing it in an audit dashboard.

Built in 5 phases; see `docs/NOTES_PHASE1.md`–`NOTES_PHASE5.md` for the
detailed design rationale, bugs found, and testing evidence behind each one
— written specifically to speed up the dissertation write-up.

## Project structure

```
backend/      FastAPI + SQLAlchemy + SQLite. Ingests telemetry events, runs
              PII detection (regex + Presidio), scores risk, applies policy,
              tags GDPR articles. Only ever persists redacted text.
extension/    Manifest V3 Chrome extension. One generic capture engine
              (content-scripts/engine.js) covers all 8 platforms rather than
              per-platform scrapers.
dashboard/    Streamlit app: usage stats, audit log, risk/compliance charts,
              CSV export. Reads the backend's SQLite DB read-only.
dataset/      Synthetic labeled prompt dataset + evaluation scripts
              (regex-only baseline vs hybrid detector: precision/recall/F1,
              false-positive analysis, latency).
docs/         Phase-by-phase implementation notes + the manual testing guide.
```

## Running it locally

All three components share one Python venv at `backend/venv`.

**Backend:**
```bash
cd backend
./venv/Scripts/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```
API docs at http://127.0.0.1:8000/docs. Config in `backend/.env` (copy from
`.env.example`) and `backend/policy.yaml` (risk thresholds, blocked
categories, allowed platforms).

**Dashboard:**
```bash
cd dashboard
../backend/venv/Scripts/python -m streamlit run app.py --server.port 8501
```
http://127.0.0.1:8501 — needs at least one event in the database (ingest one
via the API or the extension first).

**Extension:** `chrome://extensions` → Developer mode → Load unpacked →
select the `extension/` folder. Full walkthrough, including safe fake-PII
values to test with (don't type real personal data into real LLM
platforms), in [docs/TESTING_GUIDE.md](docs/TESTING_GUIDE.md).

## Evaluation headline

Hybrid detection (regex + Microsoft Presidio + contextual keyword scoring)
vs. a regex-only baseline, on a 368-prompt synthetic labeled dataset:

| | Baseline | Hybrid |
|---|---|---|
| Per-category F1 (micro) | 0.667 | 0.940 |
| Prompt-level F1 (any detection) | 0.738 | 0.970 |
| Mean scan latency | 0.07 ms | 15.5 ms |

Full methodology, false-positive analysis, and threshold-calibration
discussion in [docs/NOTES_PHASE5.md](docs/NOTES_PHASE5.md); raw results and
charts in `dataset/results/`.

## Security of the tool itself

Detecting sensitive data and being securely built are different questions —
[docs/NOTES_SECURITY.md](docs/NOTES_SECURITY.md) covers a dedicated review of
the latter across two passes: dependency/static-analysis scans (pip-audit,
Bandit, npm audit — all clean or false-positive), a timing-attack fix in the
API key check, closing the dashboard's previously-nonexistent authentication
(now with brute-force lockout and session timeout), tightening CORS from a
wide-open wildcard to an explicit allowlist, per-IP rate limiting, input
length limits, security response headers, and a GitHub Actions workflow that
re-runs the scans on every push — plus what was deliberately left out of
scope (TLS, per-user credentials, full encryption at rest) and the reasoning
for each.

## Key design decisions worth knowing before reading the code

- **No raw prompt text is ever persisted** — only a redacted copy plus a
  one-way SHA-256 hash of the original, verified directly against the
  SQLite schema in Phase 1.
- **One generic capture engine, not 8 per-platform scrapers** (Phase 2) —
  ChatGPT/Claude wall their compose UI behind login, so hand-tuned selectors
  written from memory were judged too risky to ship; a semantic-heuristic
  engine (Enter-to-send / send-button click, on whichever textarea/
  contenteditable is active) covers all 8 platforms from one script instead.
- **Regex and Presidio are scoped to disjoint entity types** (Phase 3) —
  regex owns structured/deterministic formats (UK NI numbers, credit cards
  with Luhn validation, AWS keys), Presidio owns NLP/NER-based unstructured
  entities (names, locations) regex fundamentally can't do. Standalone
  testing showed Presidio's own phone-number recognizer misfiring on NHS
  numbers, which is what justified keeping the two detectors' scopes
  separate rather than letting them compete over the same spans.
- **GDPR article mapping is illustrative, not legal advice** (Phase 3) —
  explicitly documented as such in `backend/app/gdpr.py`.
