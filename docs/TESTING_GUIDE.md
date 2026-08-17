# Manual Testing Guide

This document describes the procedure used to verify the PromptGuard
pipeline end-to-end — backend, dashboard, and Chrome extension — against
the real target platforms. It assumes the backend (`:8000`) and dashboard
(`:8501`) are already running locally.

**Test data constraint.** Because the real ChatGPT/Claude/etc. interfaces
are genuine third-party services, any text submitted during testing is
actually transmitted to those providers. Testing therefore used only
synthetic placeholder values — the same ones used in the evaluation dataset
(Chapter 5) — which are safe because they are industry-standard or
officially-reserved fakes, not because they are secret:

| Category | Test value used |
|---|---|
| Email | `alice@example.com` |
| UK phone | `07700 900123` (Ofcom's fiction-reserved mobile range) |
| NI number | `AB123456C` |
| Credit card | `4111111111111111` (standard Visa test number) |
| AWS key | `AKIAIOSFODNN7EXAMPLE` (AWS's own documentation example) |
| Name | `John Smith` / `Jane Doe` |
| NHS number | `943 476 5919` |

---

## Part 1 — Backend sanity check

The API's health endpoint is checked first, before testing anything built
on top of it:

```bash
curl http://127.0.0.1:8000/health
```

Expected result: `{"status":"ok"}`.

A test event is then sent directly, bypassing the extension entirely, to
confirm the detection pipeline itself is healthy:

```bash
curl -X POST http://127.0.0.1:8000/events/ingest \
  -H "Content-Type: application/json" \
  -H "X-API-Key: change-me-dev-key" \
  -d '{"external_user_id":"manual-test","platform":"chatgpt","text":"My email is alice@example.com and my card is 4111111111111111"}'
```

**Correct behaviour:** the response JSON shows `redacted_text` with
`[EMAIL_REDACTED]` and `[CREDIT_CARD_REDACTED]` in place of the real
values, `detections` listing both categories, and `risk_score.risk_level`
at `"medium"` or higher with `policy_violation: true` (credit card is a
blocked category). A failure at this stage indicates a problem in the
backend itself, prior to any extension-specific testing.

The interactive API documentation at **http://127.0.0.1:8000/docs** can
also be used to exercise endpoints without curl.

---

## Part 2 — Load the Chrome extension

1. Navigate to `chrome://extensions`.
2. Enable **Developer mode**.
3. Click **Load unpacked** and select the `promptguard/extension` folder.
4. Confirm "PromptGuard Monitor" appears with no errors, then pin it via
   the toolbar's puzzle-piece icon.

**Configuration check:** the extension icon → **Settings** should show
Backend URL `http://127.0.0.1:8000` and API Key `change-me-dev-key` — the
defaults, matching the backend's `.env`. No changes are needed unless the
backend's API key was changed from its default.

---

## Part 3 — Per-platform testing

For each of the 8 platforms below: log in, start a new chat, type one of
the test values from the table above into a sentence, and submit it both
by pressing Enter and by clicking the send button (across different
platforms, to exercise both capture paths in `engine.js`).

| # | Platform | URL |
|---|---|---|
| 1 | ChatGPT | https://chatgpt.com |
| 2 | Claude | https://claude.ai |
| 3 | Gemini | https://gemini.google.com |
| 4 | Copilot | https://copilot.microsoft.com |
| 5 | Perplexity | https://www.perplexity.ai |
| 6 | DeepSeek | https://chat.deepseek.com |
| 7 | Grok | https://grok.com |
| 8 | Mistral Le Chat | https://chat.mistral.ai |

**Example prompt:** `Please help me draft a reply, my email is alice@example.com`

### Verification points, per submission

**1. Extension popup.** Immediately after submission, the popup should
show:
```
Last capture: <platform> — risk: <level> (<timestamp>)
```
in green. A red/"failed" result, with the platform and error message
noted, indicates a `PLATFORM_MAP` override is needed (see Troubleshooting
below).

**2. Dashboard** (http://127.0.0.1:8501, data cached for 10s). The **Audit
Log** tab should show a new row for that platform, with:
- the correct platform name
- `redacted_text` showing `[EMAIL_REDACTED]` (or the relevant category) —
  never the raw typed value
- a sensible `risk_level`

**3. Raw API**, to check independently of the dashboard's cache:
```bash
curl "http://127.0.0.1:8000/events?limit=5" -H "X-API-Key: change-me-dev-key"
```

### Pass criteria per platform

- Enter (no Shift) submits and is captured
- Clicking the visible send button also submits and is captured
- Captured text is correctly redacted (raw PII never appears in the audit
  log or in `redacted_text`)
- Multi-line input (Shift+Enter for a newline, then Enter to send) does not
  trigger a false capture on the Shift+Enter keystroke

### Platform not captured

The generic engine (`extension/content-scripts/engine.js`) detects the
active `<textarea>`/`contenteditable` and a click on anything whose
accessible name contains "send"/"submit". If a platform's send button is
icon-only with no `aria-label`/`title` containing "send", the click path
will not fire (Enter-to-send remains a fallback).

Diagnosis: inspect the send button via DevTools (F12 → Elements) and check
its `aria-label`/`title`. If it uses different wording, the fix is either
adding that label text to the regex in `isSendTrigger()` in `engine.js`, or
a per-platform selector override — a one-line change, not a rewrite, per
the architecture rationale in `docs/NOTES_PHASE2.md`.

---

## Part 4 — Dashboard walkthrough

With real data from Part 3 in the database:

1. **Overview tab** — KPI tiles reflect real totals; the "Events by
   platform" bar chart shows a bar for every platform tested, in the fixed
   colour order (ChatGPT=blue, Claude=orange, Gemini=aqua, Copilot=yellow,
   Perplexity=magenta, DeepSeek=green, Grok=violet, Mistral=red).
2. **Audit Log tab** — sidebar filters (platform/user/risk level) update
   the table correctly; the "Event detail" selector's Detections/GDPR tags
   match what was submitted; the **Download CSV** button produces a file
   containing redacted text only, no raw PII.
3. **Trends & Compliance tab** — the stacked bar reflects test events by
   day/risk level; category frequency and GDPR article charts reflect the
   categories actually triggered.

---

## Part 5 — Extension resource usage

This requires Chrome's built-in task manager rather than an automated
profiler, since it must be measured against a real, authenticated browser
session:

1. Open Chrome's task manager (**Shift+Esc**, or Chrome menu → More Tools
   → Task Manager).
2. Locate "PromptGuard Monitor" (may appear under the extension name or as
   a background service worker).
3. Record memory and CPU% at idle, and again while actively submitting on
   a platform tab.
4. A small number of readings (idle vs. active, across 2-3 platforms) is
   sufficient to establish that a DOM-event-listener-based extension has
   negligible overhead — this is not intended as a rigorous profiling
   study.

---

## Test record

- [ ] Backend health check passes
- [ ] Manual ingest test shows correct redaction and risk scoring
- [ ] Extension loads with no console errors
- [ ] ChatGPT: Enter-to-send capture works
- [ ] ChatGPT: click-to-send capture works
- [ ] Claude: capture works
- [ ] Gemini: capture works
- [ ] Copilot: capture works
- [ ] Perplexity: capture works
- [ ] DeepSeek: capture works
- [ ] Grok: capture works
- [ ] Mistral: capture works
- [ ] Dashboard Overview reflects real data correctly
- [ ] Dashboard Audit Log filters and CSV export work
- [ ] Dashboard Trends charts reflect real data correctly
- [ ] Chrome task manager readings recorded for at least 2-3 platforms
