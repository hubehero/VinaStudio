# VinaStudio 0.6.6 quality batch — 2026-11-02

This is the development record for the post-0.6.5 quality pass. It is **not** a
released artifact and does not relabel the 0.6.5 release evidence.

## Evidence

- Backend: **857 passed / 0 failed / 0 errors / 0 skipped** (499.0 s).
- Frontend: **9 files / 28 tests passed**.
- `ruff`, `vue-tsc`, `vite build`: passed.
- Public backend smoke: passed (`validation/ci/smoke.py`).
- Playwright production-build browser smoke: **2 passed** (10.9 s); evidence `raw/e2e.log`.
- Release-tree preflight for 0.6.6: passed.

## Changes captured

- New docking runs default to **seed 42**; `0` remains the explicit random mode.
- Completed `job.json` records software/runtime versions, engine, seed, input
  hashes and roster identity.
- Job history exposes indexed storage size and confirmed deletion of **terminal**
  jobs only. Running jobs and unindexed preparation directories are rejected.
- The release tree runs a small backend smoke without Qt/network/full docking.
- Catalog rebuild creates a timestamped `catalog.sqlite.bak-*` before importing.
- Workspace migration verifies the copied file inventory before switching.

The full 125-member screening and interaction-level screenshots remain in
`../2026-10-30/`; they were not re-run for a UI/quality-only patch. The 1IEP
software-control rerun for 0.6.5 is in `../2026-11-02-v0.6.5/`.
