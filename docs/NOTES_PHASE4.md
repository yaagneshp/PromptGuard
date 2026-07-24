# Implementation Notes — Phase 4: Dashboard

## Stack and structure

Streamlit app in `dashboard/`, reading directly from the backend's SQLite
file (`backend/promptguard.db`) rather than going through the FastAPI API.
For a local single-machine MVP this is simpler than adding read endpoints to
the backend just to re-serve data the dashboard can query directly, and
keeps the dashboard fully decoupled — it never writes, so it can't corrupt
backend state.

- `db.py` — opens the SQLite file with a **read-only URI connection**
  (`file:...?mode=ro`), so a dashboard bug can never write to the backend's
  live data. Three loader functions (`load_events`, `load_detections`,
  `load_compliance_tags`) return pandas DataFrames via `pd.read_sql_query`.
- `colors.py` — the project's status palette (risk levels) and categorical
  palette (platforms), pulled from the dataviz design-system reference
  (`references/palette.md`) rather than picked by eye. Both sets pass
  adjacent-pair colorblind-safety checks in light mode per that reference.
- `app.py` — single-file Streamlit app: sidebar filters (platform, user, risk
  level, policy-violation-only, date range) apply across three tabs
  (Overview, Audit Log, Trends & Compliance).

Runs from the **same venv as the backend** (`backend/venv`) rather than a
separate one — this is a single-developer local MVP, not a service that
needs independent deployment/scaling from the backend, so a second venv
would just be bookkeeping overhead for no benefit. `dashboard/requirements.txt`
documents the three added packages (streamlit, plotly, pandas) for
reproducibility even though they're installed into the shared venv.

**Enabled WAL mode on the backend's SQLite connection**
([database.py](../backend/app/database.py)) so the dashboard's read-only
connection doesn't contend for locks with the backend's writes while both
run concurrently — relevant for live demos where the extension/curl is
ingesting events while the dashboard is open.

## Color usage (per the project's dataviz method)

- **Risk level** (low/medium/high/critical) uses the fixed **status palette**
  (green/amber/orange/red) everywhere it appears — bar charts, stacked bars —
  never reused for anything else.
- **Platform** identity uses the validated 8-slot **categorical palette** in
  fixed order, via `color_discrete_map` + `category_orders` so the color
  always follows the platform, never its rank in the current filter.
- **Category frequency** and **GDPR article breakdown** are magnitude
  comparisons (bar length already carries the comparison, axis labels
  already carry identity) — deliberately single-hue (sequential blue) rather
  than inventing extra categorical colors for >8 categories, which the
  palette's own rules say not to do (fold to "Other"/facet past 8 adjacent
  categories, not cycle the palette).

## A real bug caught during visual testing

The "events over time by risk level" chart initially used `px.area()` and
rendered **completely empty**, with the x-axis showing nonsense tick labels
like `23:59:59.999` and `00:00:00.0005`. Root cause, found by actually
opening the dashboard in a browser rather than trusting the code:

1. All test data happened to land on a single calendar day (normal for an
   early-testing dataset).
2. Plotly Express infers axis type from the **data's content**, not the
   pandas dtype — even after casting the day column to a plain string, a
   date-shaped string still gets auto-detected as a temporal axis.
3. A temporal axis with only one distinct value collapses to a near-zero
   range, and Plotly's autorange padding on that zero-width range produces
   sub-second tick labels.
4. Separately, even after forcing `fig.update_xaxes(type="category")` to fix
   the axis labels, the chart *still* rendered empty — because an **area**
   chart fundamentally needs ≥2 x-points to draw a filled shape; one x-point
   draws nothing.

Fixed by switching to a **stacked bar chart** (`px.bar` with
`update_xaxes(type="category")`), which renders correctly regardless of how
many distinct days exist in the data. This will remain correct once Phase 5
evaluation data accumulates across multiple days — bars just get more x-ticks.

This is worth a sentence in the dissertation's methodology/testing section:
static code review would not have caught this, since the code ran without
raising an exception — the chart silently rendered nothing. Only opening the
actual rendered page surfaced it.

## Testing performed

Manual, via the in-browser preview (no automated UI test suite for the
dashboard — reasonable given this is a Streamlit app whose "correctness" is
largely visual/layout, and time was tighter than for the backend/extension):
seeded 17 events across 5 users, 9 platforms (8 valid + 1 deliberately
disallowed), and a spread of risk levels/policy violations, then verified in
the running app:
- Overview: KPI tiles, events-by-platform bar (correct categorical colors,
  correct counts), risk-level distribution bar (correct status colors),
  per-user breakdown table (correct aggregates, including the pseudonymous
  UUID left over from the Phase 2 extension integration test — confirms the
  dashboard reads real end-to-end pipeline data, not just curl-seeded rows).
- Audit Log: filtered table renders and sorts correctly; event-detail
  selector correctly surfaces per-event detections + GDPR tags; **CSV export
  verified by actually clicking the button and inspecting the downloaded
  file's contents** — correct columns, correctly redacted text, no raw PII.
- Trends & Compliance: risk-level stacked bar (after the fix above), PII
  category frequency bar, GDPR article breakdown bar — all correct after
  switching to single-hue sequential color for the two magnitude-only charts.

## Known limitations / future work

- No automated dashboard tests — worth a Selenium/Playwright smoke test if
  the dashboard grows more interactive logic.
- Filters recompute on every widget interaction (Streamlit's default rerun
  model) — fine at current data volume; would want the SQL queries
  parameterized by filter (pushed down to SQLite) rather than filtering the
  full in-memory DataFrame if the event volume grows large ahead of Phase 5's
  evaluation dataset.
- No dark/light theme handling beyond Streamlit's own default theming — not
  a concern for a local demo tool.
