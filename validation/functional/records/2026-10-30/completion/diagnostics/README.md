# Diagnostics feature evidence — 2026-10-30

The Environment page now exposes a user-triggered diagnosis:

- `GET /api/system/diagnostics` is read-only.
- `POST /api/system/diagnostics/repair` only creates missing application and
  workspace directories, then re-runs the same checks.
- Corrupt configuration, catalog or job indexes are reported and left untouched;
  the UI states the reason and a recovery suggestion.

The screenshot `environment-diagnostics.png` shows the production build with 11
checks (including the browser WebGL renderer check) all healthy after repair.
`environment-diagnostics-repaired.png` retains the repair confirmation from the
same flow. Unit and integration coverage:

- `tests/unit/test_diagnostics.py`
- `tests/integration/test_diagnostics_api.py`

## Automated result

- Backend: **830 passed / 0 failed / 0 errors / 0 skipped**, 370.0 s.
- Frontend: **9 files / 27 tests passed**; `vite build` passed.
- `ruff`: passed.

The diagnostic report contains 10 server-side checks plus the browser WebGL
renderer check (11 rows in the production UI). The safe repair path creates
missing app/workspace directories; it does not touch configuration, catalog,
job indexes or result data.
