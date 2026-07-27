# Manual Testing Guide

Step-by-step instructions for verifying the whole PromptGuard pipeline
end-to-end: backend, dashboard, and the Chrome extension against the real
platforms. The backend (`:8000`) and dashboard (`:8501`) are already running
locally as you left them.

**Important — use fake data, not real PII.** Whatever you type into the real
ChatGPT/Claude/etc. UIs is actually sent to OpenAI/Anthropic/Google/Microsoft/
etc. as a real prompt. Don't type your real email, phone number, or card
details to test this. Use the same placeholder values the dissertation
dataset uses — they're safe precisely because they're industry-standard or
officially-reserved fakes, not because they're secret:

| Category | Safe test value |
|---|---|
| Email | `alice@example.com` |
| UK phone | `07700 900123` (Ofcom's fiction-reserved mobile range) |
| NI number | `AB123456C` |
| Credit card | `4111111111111111` (standard Visa test number) |
| AWS key | `AKIAIOSFODNN7EXAMPLE` (AWS's own documentation example) |
| Name | `John Smith` / `Jane Doe` |
| NHS number | `943 476 5919` |

---

## Part 1 — Backend sanity check (2 minutes)

**If you're using PowerShell** (the default on Windows — your prompt looks
like `PS C:\Users\...>`), `curl` is aliased to `Invoke-WebRequest`, which
doesn't accept `-X`/`-H`/`-d` the same way `curl` does, and PowerShell
doesn't support backslash line-continuation at all (only backtick `` ` ``).
Use the PowerShell-native commands below instead of the `bash` ones.
**If you're in Git Bash / WSL**, the `bash` blocks work as-is.

Confirm the API is actually up and responding before testing anything on
top of it:

```bash
curl http://127.0.0.1:8000/health
```

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/health"
```

Expect: `{"status":"ok"}` (bash) or a table with `status: ok` (PowerShell).

Then send one test event directly, bypassing the extension entirely, to
confirm the detection pipeline itself is healthy:

```bash
curl -X POST http://127.0.0.1:8000/events/ingest \
  -H "Content-Type: application/json" \
  -H "X-API-Key: change-me-dev-key" \
  -d '{"external_user_id":"manual-test","platform":"chatgpt","text":"My email is alice@example.com and my card is 4111111111111111"}'
```

```powershell
$headers = @{ "Content-Type" = "application/json"; "X-API-Key" = "change-me-dev-key" }
$body = '{"external_user_id":"manual-test","platform":"chatgpt","text":"My email is alice@example.com and my card is 4111111111111111"}'
Invoke-RestMethod -Uri "http://127.0.0.1:8000/events/ingest" -Method Post -Headers $headers -Body $body | ConvertTo-Json -Depth 6
```

**What "working correctly" looks like:** the response JSON should show
`redacted_text` with `[EMAIL_REDACTED]` and `[CREDIT_CARD_REDACTED]` in
place of the real values, `detections` listing both categories, and
`risk_score.risk_level` at `"medium"` or higher with `policy_violation: true`
(credit card is a blocked category). If any of that's missing, something's
broken before you even get to the extension — stop and flag it rather than
debugging the extension first.

You can also browse the interactive API docs at
**http://127.0.0.1:8000/docs** to try endpoints from a UI instead of curl.

---

## Part 2 — Load the Chrome extension (5 minutes)

1. Open Chrome and go to `chrome://extensions`
2. Toggle **Developer mode** on (top-right corner)
3. Click **Load unpacked**
4. Select the `promptguard/extension` folder
5. You should see "PromptGuard Monitor" appear in your extensions list with
   no errors. Click the puzzle-piece icon in Chrome's toolbar and pin it so
   the popup is one click away.

**Check the config matches your running backend:** click the extension icon
→ **Settings**. It should show:
- Backend URL: `http://127.0.0.1:8000`
- API Key: `change-me-dev-key`

These are the defaults and already match your `.env` — you shouldn't need to
change anything unless you changed the backend's API key.

---

## Part 3 — Test each platform (the main event)

For each of the 8 platforms below: log in normally, start a new chat, type
one of the safe test values from the table above into a sentence, and submit
it exactly the way you normally would (press Enter, or click the send
button — try both across different platforms so you exercise both capture
paths in `engine.js`).

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

**Example prompt to type:** `Please help me draft a reply, my email is alice@example.com`

### After each submission, check three things:

**1. The extension popup.** Click the extension icon immediately after
submitting. It should show:
```
Last capture: <platform> — risk: <level> (<timestamp>)
```
in green. If it shows red/"failed", note the platform and the error message
— that's the signal something needs a `PLATFORM_MAP` override (see
Troubleshooting below).

**2. The dashboard** (http://127.0.0.1:8501 — refresh the page, data is
cached for 10s). Go to the **Audit Log** tab and confirm a new row appeared
for that platform with:
- the correct platform name
- `redacted_text` showing `[EMAIL_REDACTED]` (or whatever category you
  tested) — **never** your actual typed value
- a sensible `risk_level`

**3. The raw API**, if you want to double check without relying on the
dashboard's 10-second cache:
```bash
curl "http://127.0.0.1:8000/events?limit=5" -H "X-API-Key: change-me-dev-key"
```
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/events?limit=5" -Headers @{ "X-API-Key" = "change-me-dev-key" } | ConvertTo-Json -Depth 6
```

### What counts as a pass per platform

- Typing + pressing Enter (no Shift) submits and gets captured
- Typing + clicking the visible send button also submits and gets captured
- The captured text is correctly redacted (raw PII never appears in the
  audit log or in `redacted_text`)
- Multi-line prompts (Shift+Enter for a newline, then Enter to send) don't
  trigger a false capture on the Shift+Enter keystroke

### If a platform doesn't get captured

The generic engine (`extension/content-scripts/engine.js`) detects the
active `<textarea>`/`contenteditable` and a click on anything whose
accessible name contains "send"/"submit". If a specific platform's send
button is icon-only with no `aria-label`/`title` containing "send", the
click path won't fire (Enter-to-send should still work as a fallback).

To fix: open DevTools on that platform (F12 → Elements), inspect the send
button, and check its `aria-label`/`title`. If it's something else (e.g.
just "Go"), that's the concrete, minimal fix — either add that label text to
the regex in `isSendTrigger()` in `engine.js`, or add a per-platform
selector override. This is a one-line fix, not a rewrite — the architecture
was deliberately built this way (see `docs/NOTES_PHASE2.md` for why).

---

## Part 4 — Dashboard walkthrough

With real data from Part 3 now in the database:

1. **Overview tab** — KPI tiles should reflect real totals. The
   "Events by platform" bar chart should show a bar for every platform you
   tested, in the fixed color order (ChatGPT=blue, Claude=orange, Gemini=aqua,
   Copilot=yellow, Perplexity=magenta, DeepSeek=green, Grok=violet,
   Mistral=red).
2. **Audit Log tab** — filter by platform/user/risk level in the sidebar and
   confirm the table updates. Pick an event ID in the "Event detail"
   selector and confirm its Detections/GDPR tags match what you'd expect
   from what you typed. Try the **Download CSV** button and open the file —
   confirm redacted text only, no raw PII.
3. **Trends & Compliance tab** — the stacked bar should show your test
   events grouped by day/risk level; category frequency and GDPR article
   charts should reflect the categories you actually triggered.

---

## Part 5 — Extension resource usage (the one thing I can't measure for you)

Since I can't attach a profiler to your real Chrome session:

1. Open Chrome's own task manager: **Shift+Esc** (or Chrome menu → More
   Tools → Task Manager)
2. Find "PromptGuard Monitor" in the list (may show as the extension name
   or as a background service worker)
3. Note its memory and CPU% at idle, and again while actively typing/
   submitting on a platform tab
4. For the dissertation's resource-usage evaluation, a few readings (idle
   vs active, across 2-3 platforms) is enough — you're establishing that a
   DOM-event-listener-based extension has negligible overhead, not doing
   a rigorous profiling study

---

## Quick checklist to fill in as you go

- [ ] Backend health check passes
- [ ] Manual curl ingest test shows correct redaction + risk scoring
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
- [ ] Dashboard Audit Log filters + CSV export work
- [ ] Dashboard Trends charts reflect real data correctly
- [ ] Chrome task manager readings noted for at least 2-3 platforms

Anything that fails, tell me which line item and what you saw (screenshot of
the popup/console error is ideal) and I'll fix it.
