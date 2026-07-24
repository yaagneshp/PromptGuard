# Implementation Notes — Phase 2: Chrome Extension

## Architecture decision: one generic capture engine, not 8 bespoke scrapers

The original plan called for tuning platform-specific DOM selectors on ChatGPT
and Claude first, then repeating the pattern for the other 6. In practice this
wasn't feasible in the time available: both ChatGPT and Claude wall their
compose UI behind a login (verified live — ChatGPT's "Try it first" link
loops back to `/auth/login`; claude.ai redirects straight to a sign-in page),
and I cannot sign into the user's accounts myself (credential entry is
explicitly off-limits). Hand-tuned selectors written against memory/guesses
rather than the live DOM would be a real risk of shipping non-functional
detectors, so the design was changed instead of the schedule.

**The fix:** every one of the 8 target platforms uses either a `<textarea>` or
a `contenteditable` element as its composer, and every one submits on
Enter-without-Shift or a click on a button whose accessible name is
"send"/"submit". [engine.js](../extension/content-scripts/engine.js) is a
single ~100-line script implementing that generic pattern, injected on all 8
domains via `manifest.json`'s `content_scripts.matches`. Per-platform
differentiation is now just one entry in `PLATFORM_MAP` (hostname regex →
platform key), not a separate scraper.

This is more resilient to markup churn than hardcoded selectors (worth citing
as a deliberate tradeoff in the dissertation — precision-per-platform traded
for maintainability and being buildable without live authenticated access to
every target site), at the cost of being less precise: it can occasionally
seize on the wrong composer if a page has multiple editable regions, or the
wrong button if a platform's "New chat" button happens to also expose "send"
in its accessible name. `PLATFORM_MAP` has a slot for a per-platform selector
override if that turns out to matter in practice.

## Extension structure

| File | Role |
|---|---|
| `manifest.json` | MV3 manifest; `host_permissions` scoped to the local backend only (`127.0.0.1:8000`, `localhost:8000`) |
| `content-scripts/engine.js` | Generic capture engine (see above) |
| `background.js` | Service worker: receives `PROMPT_SUBMITTED` messages, generates/persists a pseudonymous `externalUserId` (via `crypto.randomUUID()`, stored in `chrome.storage.local`), POSTs to `/events/ingest` |
| `options.html` / `options.js` | Configure backend URL + API key (`chrome.storage.sync`) |
| `popup.html` / `popup.js` | Shows the result of the last capture, for quick manual testing |

**Why the background service worker does the fetch, not the content script:**
content scripts run in the page's own origin and would be subject to the
page's CSP and cross-origin restrictions; a MV3 background service worker with
`host_permissions` for the backend origin fetches without being subject to
page-level CORS at all. `CORSMiddleware` was still added to the FastAPI app
([main.py](../backend/app/main.py)) as defense-in-depth and to satisfy direct
browser-based testing (e.g. hitting the API from devtools on a target site) —
currently wide open (`allow_origins=["*"]`), which is fine for a local MVP but
should be scoped to the specific `chrome-extension://<id>` origin before any
real deployment.

## Testing performed

Since I cannot log into ChatGPT/Claude/etc. to test against the real live
DOM, testing was split into two halves that together cover the whole pipeline
except the "real site, real login" step:

1. **`extension/tests/engine.test.js`** (jsdom, 13 assertions, all passing) —
   loads `engine.js` into a synthetic DOM built with jsdom for each platform
   hostname and exercises:
   - textarea + Enter → captures correctly, correct platform tag
   - Shift+Enter → correctly does *not* submit (newline case)
   - contenteditable composer + Enter → captures correctly
   - click on an icon nested inside a `button[aria-label="Send message"]` →
     correctly resolves to the ancestor button and submits (this is the
     common real-world pattern: an SVG icon inside the send button, not a
     text label directly on it)
   - click on an unrelated button (e.g. "New chat") → correctly does *not* submit
   - empty/whitespace-only composer → correctly does *not* submit
   - unmapped hostname → falls back to `platform: "unknown"` rather than crashing
2. **`extension/tests/background.test.js`** (Node + native `fetch`, run against
   the live local backend, all passing) — mocks `chrome.storage`/`chrome.runtime`
   and calls `background.js`'s real `onMessage` handler with a
   `PROMPT_SUBMITTED` message containing an AWS key + credit card number,
   confirming: the pseudonymous user ID is generated and persisted, the POST
   to `/events/ingest` succeeds, the returned risk level is correct
   (`high`, 65 = AWS key 35 + credit card 30), and `lastResult` is recorded
   for the popup. Cross-checked against `GET /events` afterwards — the events
   really did land in SQLite with correct redaction.

**Not yet tested:** the extension loaded as an actual unpacked Chrome
extension against the real, authenticated ChatGPT/Claude/Gemini/Copilot/
Perplexity/DeepSeek/Grok/Mistral UIs. That requires your own logged-in browser
sessions. To do it:

```
chrome://extensions → Developer mode → Load unpacked → select the
`extension/` folder
```

Then open each platform, type a prompt containing some fake PII, submit it,
and check the popup and `GET /events` for the captured event. If the generic
engine misses on a specific platform (e.g. doesn't detect the composer, or
the send button's accessible name doesn't contain "send"/"submit"), the fix
is a one-line override in `PLATFORM_MAP`, not a rewrite.

## Known limitations / future work

- `host_permissions` is hardcoded to localhost — pointing the extension at a
  deployed backend URL via the options page won't work until
  `optional_host_permissions` + a runtime `chrome.permissions.request` flow is
  added (fine for local MVP, a gap for real deployment).
- No de-duplication across page reloads — the 800ms same-text debounce in
  `engine.js` only guards against a single submission firing the listener
  twice, not against a user submitting the exact same prompt twice on
  purpose (which is intentionally still captured).
- CORS is wide open (`allow_origins=["*"]`) — acceptable for local MVP, not
  for a real deployment.
