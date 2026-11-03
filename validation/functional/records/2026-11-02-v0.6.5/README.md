# VinaStudio 0.6.5 evidence — 2026-11-02

**Software:** VinaStudio 0.6.5  
**Development commit:** `94ccd73` (clean)  
**Release commit/tag:** `1021850` / `v0.6.5`  
**Purpose:** version-aligned software-control evidence, not a docking-accuracy benchmark.

## What is in this record

- `environment.json` — runtime, commit, input hashes and commands.
- `validation-report.json` / `.md` — clean 1IEP rerun on 0.6.5:
  **−13.286 kcal/mol**, **0.353 Å** top-pose RMSD, 5 poses, 0 geometry errors.
- `raw/pytest-junit.xml` / `raw/pytest.log` — **830 passed** backend suite.
- `raw/frontend-test.log` / `raw/frontend-build.log` — **27 passed**, build green.
- `ui/diagnostics.png` — 0.6.5 production UI diagnostics, 11 checks healthy.
- `inputs.sha256` — committed 1IEP and manifest hashes.

## Historical boundary

The interaction-level UI walkthrough, full 125-member screening, batch, providers
and desktop smoke are retained in
[`../2026-10-30/`](../2026-10-30/) and its `completion/` phase. Those observations
were made on the 0.6.4 validation tree plus a patch; 0.6.5 changed the diagnostics
feature and release metadata, not the docking/analysis protocol. This record does
**not** relabel that historical evidence as freshly executed on 0.6.5.

The 1IEP result remains a single-target software control with a crystallographic
reference whose coordinates are PDB-derived but whose bond orders/charge come
from the tutorial SDF. It does not support general accuracy, enrichment or
experimental-affinity claims.

## Reproduce

```bash
uv sync --extra dev
uv run pytest -q
pnpm -C web typecheck
pnpm -C web test
pnpm -C web build
uv run python scripts/validate_benchmark.py --case 1iep \
  --out-dir validation-output/0.6.5-2026-11-02
```
