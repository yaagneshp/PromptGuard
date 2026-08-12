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

## File guide

### Root

| File | Purpose |
|---|---|
| `README.md` | This file |
| `.gitignore` | Excludes `venv/`, `.env`, `*.db`, `node_modules/`, etc. from git |
| `.github/workflows/security-scan.yml` | CI workflow — runs pip-audit, Bandit, and npm audit on every push/PR |

### `backend/` — the FastAPI service

| File | Purpose |
|---|---|
| `app/main.py` | The FastAPI app — endpoints, CORS, security headers, rate limiting, lifespan startup |
| `app/models.py` | SQLAlchemy schema (users, platforms, events, detections, risk_scores, compliance_tags) |
| `app/schemas.py` | Pydantic request/response validation, including input-length/charset limits |
| `app/crud.py` | Database read/write operations |
| `app/auth.py` | API key authentication (constant-time comparison) |
| `app/config.py` | Settings loaded from `.env` |
| `app/database.py` | DB connection setup — WAL mode, file permission hardening |
| `app/policy.py` | Loads `policy.yaml` (risk thresholds, blocked categories, allowed platforms) |
| `app/risk.py` | The hybrid risk-scoring formula |
| `app/gdpr.py` | Category → UK GDPR article mapping |
| `app/ratelimit.py` | Per-IP rate limiter configuration |
| `app/detectors/regex_detectors.py` | The 7 regex-based PII detectors |
| `app/detectors/presidio_detector.py` | Presidio/NER wrapper, scoped to its specific entity set |
| `app/detectors/combined.py` | Merges regex + Presidio matches into one redaction pass |
| `policy.yaml` | The actual policy configuration (data, not code) |
| `requirements.txt` | Pinned Python dependencies |
| `.env.example` | Template showing what `.env` needs (`.env` itself is gitignored) |
| `tests/test_presidio_standalone.py` | Standalone Presidio smoke test from Phase 3 |

### `extension/` — the Chrome extension

| File | Purpose |
|---|---|
| `manifest.json` | MV3 manifest — permissions, content script registration |
| `content-scripts/engine.js` | The generic capture engine (works across all 8 platforms) |
| `background.js` | Service worker — generates the pseudonymous user ID, POSTs to the backend |
| `options.html` / `.js` | Settings page (backend URL, API key) |
| `popup.html` / `.js` | Shows the result of the last capture |
| `tests/engine.test.js` | 13 jsdom unit tests for the capture logic |
| `tests/background.test.js` | Integration test against the live backend |

### `dashboard/` — the Streamlit app

| File | Purpose |
|---|---|
| `app.py` | Main dashboard — Overview, Audit Log, and Trends & Compliance tabs |
| `auth.py` | Password gate with brute-force lockout and session timeout |
| `db.py` | Read-only SQLite connection to the backend's database |
| `colors.py` | The fixed status/categorical colour palette used across all charts |
| `.env.example` | Template for the dashboard password config |

### `dataset/` — the Phase 5 evaluation

| File | Purpose |
|---|---|
| `generate_dataset.py` | Builds the 368-prompt synthetic labelled dataset |
| `prompts.jsonl` | The dataset itself |
| `evaluate.py` | Runs both detectors against it and computes every metric behind the Evaluation chapter |
| `build_charts.py` | Generates the 5 evaluation charts |
| `results/` | Raw output — metrics JSON, charts, per-prompt results, `summary.md` |

### `docs/` — implementation notes

| File | Purpose |
|---|---|
| `NOTES_PHASE1.md` – `NOTES_PHASE5.md` | Phase-by-phase design rationale, bugs found, and testing evidence |
| `NOTES_SECURITY.md` | The full two-round security review write-up |
| `TESTING_GUIDE.md` | Manual step-by-step testing instructions, including safe placeholder PII values |
