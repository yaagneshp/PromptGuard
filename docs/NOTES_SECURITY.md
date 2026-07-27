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

## Round 2 — static analysis + remaining gaps

Prompted by asking "what other security issues are left" after round 1.
Ran actual tools rather than speculating further:

**Bandit** (static analysis, `bandit -r backend/app`) found exactly one
issue: `[B105:hardcoded_password_string]` on `"token_url": 25` in
`risk.py`'s category-weight dictionary. This is a false positive — Bandit's
heuristic flags any dict key containing the substring "token" as a possible
hardcoded credential, and this is a PII-category severity weight, not a
secret. Recorded here deliberately: a static analyzer's output still needs
human judgement, not blind fixing (or blind dismissal) of every finding —
a legitimate methodology point for a security dissertation.

**npm audit** (`extension/tests`, the jsdom-based test dependencies): 0
vulnerabilities.

**Fixes applied:**

- **No input length limits.** `IngestRequest` (`backend/app/schemas.py`) had
  no `max_length` on `text`, `platform`, or `external_user_id` — a single
  oversized request could tie up the Presidio/spaCy pipeline without needing
  repeated requests. Added `max_length=50_000` on `text` (generous for any
  realistic single prompt, bounds worst-case NER cost), `max_length=128`/`64`
  matching the DB column widths on the two ID fields, plus a
  `[A-Za-z0-9_-]+` charset pattern on both to reject malformed/oversized
  identifiers outright. Verified: a 60,000-char payload is now rejected with
  `422 String should have at most 50000 characters`.
- **No rate limiting.** Added per-IP limiting via `slowapi`
  (`backend/app/ratelimit.py`): 30/minute on `/events/ingest`, 60/minute on
  `GET /events`. This also throttles brute-force API-key guessing, since a
  failed auth attempt still counts against the same per-IP limit. Verified
  by sending 35 requests in a burst: the first 30 return `200`, the rest
  `429`.
- **No visibility into failed auth attempts.** `require_api_key` now logs a
  warning (`logger.warning(...)`, includes the client IP) on every rejected
  key, rather than failing silently.
- **No security response headers.** Added `X-Content-Type-Options: nosniff`,
  `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer` via a small
  middleware in `main.py`. Low-priority for a pure JSON API (nothing here
  serves HTML), but cheap and standard practice — verified present via
  `curl -i`.
- **Dashboard had no brute-force protection or session expiry.**
  `dashboard/auth.py` now locks out for 30s after 5 failed password attempts,
  and expires an authenticated session after 30 minutes idle. Verified
  in-browser end-to-end: 5 wrong passwords → "Too many failed attempts, try
  again in 30s" → correct password rejected while still locked → correct
  password accepted once the cooldown passed, full dashboard access
  restored. This is still a single-shared-password gate, not a hardened
  login system — a sufficiently patient attacker can wait out repeated 30s
  cooldowns indefinitely; a production system would want IP-based backoff
  or account lockout with alerting instead.
- **No file-level protection on the SQLite database.** Added an
  owner-only-read/write `os.chmod` call on connect (`backend/app/database.py`).
  **This is a partial, POSIX-only mitigation, not encryption at rest** — on
  Windows (this project's actual dev environment) `os.chmod` has no
  equivalent effect and this line is a no-op there. Full encryption at rest
  (e.g. SQLCipher) was evaluated and deliberately not implemented: it adds a
  native-binary dependency with known Windows wheel fragility, and — more
  fundamentally — introduces its own key-management problem (the encryption
  key becomes an equally-sensitive secret needing its own storage story, no
  better than the problem it's solving) that isn't proportionate to this
  MVP's actual threat model of a single local developer machine, not a
  multi-tenant server. This tradeoff, not a silent gap, is the point worth
  making in the dissertation.
- **No automated re-scanning.** Added
  `.github/workflows/security-scan.yml`: runs `pip-audit` + `bandit` against
  the backend and `npm audit` against the extension's test dependencies on
  every push/PR to `main`. **Caveat, stated plainly: this hasn't been
  observed running successfully on GitHub's actual runners** — I can't
  trigger or watch an Actions run from this environment, only push the
  workflow file and verify its logic manually (confirmed the underlying
  `pip-audit`/`bandit`/`npm audit` commands work correctly when run locally
  in this session). Check the Actions tab on first push to confirm it's
  green.

## Deliberately not fixed (documented, not silently ignored)

- **No TLS anywhere.** Acceptable for the current loopback-only local-demo
  deployment (traffic never leaves the machine); a real gap the moment
  either the backend or dashboard is ever exposed beyond `127.0.0.1`. The
  extension's options page also doesn't warn if `backendUrl` is pointed at
  a non-HTTPS remote endpoint.
- **Single shared API key / password, no rotation, no per-user credentials.**
  Consistent with the single-user MVP scope agreed at project start; a real
  multi-user or production deployment would need proper per-user auth.
- **`external_user_id` is client-supplied and unauthenticated.** Anyone with
  a valid API key can attribute an event to any user ID they choose — not an
  access-control hole (the key is still required), but a data-integrity/
  non-repudiation gap for a tool whose value depends on trustworthy per-user
  attribution. Mitigated only partially by the new format/length validation
  above; a real fix needs per-user credentials, which is the same
  single-user-MVP scope tradeoff as the point above.
- **No full encryption at rest.** See the SQLite file-permissions entry
  above for the reasoning.

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
