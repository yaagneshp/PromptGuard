# Security Notes

Written because this is a cybersecurity dissertation project — "does the
tool detect security-relevant data" and "is the tool itself built securely"
are two separate questions, and only the first one had been rigorously
addressed through Phases 1-5. This documents an explicit security review of
the second question, done after the functional build was complete.

## Dependency vulnerability scan

Ran `pip-audit` against `backend/requirements.txt`:

```
No known vulnerabilities found
Name           Skip Reason
en-core-web-lg Dependency not found on PyPI and could not be audited
```

`en-core-web-lg` (the spaCy language model) isn't PyPI-indexed so couldn't be
checked against a CVE database — it's Explosion AI's own official model
artifact, not arbitrary third-party code, so supply-chain risk there is
judged low. No other outstanding known-CVE dependencies at time of scan
— re-run periodically, this is a point-in-time result, not a permanent
guarantee.

## Fixed

**API key timing attack** (`backend/app/auth.py`). The original comparison
used plain `!=`, which short-circuits on the first mismatched byte —
textbook CWE-208 (timing side-channel). Replaced with
`secrets.compare_digest()`. Low real-world exploitability over a network
with typical jitter, but exactly the kind of thing worth fixing when the
fix is two lines and the project is explicitly about security.

**Dashboard had zero authentication** (`dashboard/auth.py`). The Streamlit
app showed the full audit log — per-user risk breakdowns, timestamps,
platforms, policy violations — to anyone who could reach port 8501, with no
login at all. Added a session-scoped password gate (`require_password()`,
called before any data renders), password compared via
`secrets.compare_digest`, configured via `dashboard/.env`
(`DASHBOARD_PASSWORD`, gitignored like the backend's `.env`). This is
intentionally simple — a single shared password, no user accounts — matching
the project's single-user/local-demo deployment scope agreed at the start.
Verified in-browser: wrong password shows "Incorrect password", correct
password grants access to all three tabs.

**CORS was wide open** (`allow_origins=["*"]`). Changed to a configurable
`ALLOWED_ORIGINS` setting (`backend/app/config.py`,
`allowed_origins_list` property), defaulting to **no allowed origins** rather
than a wildcard. Important nuance documented in the code: the Chrome
extension's own background service worker fetch is unaffected either way —
MV3 background workers with `host_permissions` bypass page-level CORS
entirely, which is why the extension kept working end-to-end after this
change with no configuration needed (re-verified: `background.test.js`
still 5/5 passing against the hardened backend). This setting only matters
for a hypothetical browser tab's own JS trying to call the API directly —
previously any website could have attempted that with page-context
`fetch()` and had the browser honor the response; now none can unless
explicitly added to `ALLOWED_ORIGINS`. Verified via a simulated
`Origin: https://evil.example` preflight request — no
`Access-Control-Allow-Origin` header comes back post-fix (previously
it echoed `*`).

## Deliberately not fixed (documented, not silently ignored)

- **No rate limiting / request size limits** on `/events/ingest`. Unbounded
  text into the Presidio/spaCy pipeline is a real resource-exhaustion vector
  for a genuinely adversarial deployment. Out of scope for this pass — the
  regex layer itself was checked for catastrophic-backtracking patterns
  (none of the patterns use nested unbounded quantifiers) and is not a
  concern, but the NLP layer's cost scales with input size with no cap.
- **No TLS anywhere.** Acceptable for the current loopback-only local-demo
  deployment (traffic never leaves the machine); a real gap the moment
  either the backend or dashboard is ever exposed beyond `127.0.0.1`. The
  extension's options page also doesn't warn if `backendUrl` is pointed at
  a non-HTTPS remote endpoint.
- **Single shared API key / password, no rotation, no per-user credentials.**
  Consistent with the single-user MVP scope agreed at project start; a real
  multi-user or production deployment would need proper per-user auth.

## What was already solid before this pass

- Raw prompt text is never persisted anywhere — only a redacted copy plus a
  one-way SHA-256 hash, verified directly against the SQLite schema back in
  Phase 1.
- All database access goes through the SQLAlchemy ORM (backend) or
  parameterized/static queries (dashboard) — no SQL injection surface found
  anywhere, including the dashboard's read path.
- The Chrome extension requests only the permissions it needs (`storage` +
  specific host origins) — no `<all_urls>`, no `webRequest`, no unnecessary
  API surface.
- `.env` files (both backend and dashboard) are gitignored and were never
  committed.
