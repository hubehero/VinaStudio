# Functional validation record — 2026-10-30

**Software:** VinaStudio 0.6.4  
**Source under test:** `49ff4a8` + `working-tree.patch` (`sourcePatchSha256` in
`environment.json`)  
**Platform:** Linux x86_64, Python 3.12.14, real Vina Python API  
**Purpose:** functional evidence, not an accuracy benchmark.

This re-runs on a clean checkout by following [`../README.md`](../README.md).
The SPA was served from `vinastudio/server/static` (the production bundle), not
from the Vite dev server.

## Index

> Completion phase (full 125-member screening, five-pocket site screening,
> providers, persistence, maps, desktop fallback): [`completion/README.md`](completion/README.md).
> It retains its own environment/patch hashes and is not folded into the
> original phase-1 observations.

| File | What it proves |
|---|---|
| `environment.json` | Versions, commit, dirty-tree patch hash, runtime and inputs |
| `inputs.sha256` | SHA-256 of all committed 1IEP inputs and the manifest |
| `raw/pytest.log`, `raw/pytest-junit.xml` | Full backend test run and node-level results |
| `raw/frontend.log`, `raw/repo.log` | Vitest, typecheck, Vite build, ruff, git state |
| `raw/build_web.log` | Production SPA build used for UI smoke |
| `raw/screening-b6bd0bc2b6aa.json`, `raw/screening-ranking.csv` | One-member screening run and ranking export |
| `raw/site-fddb09c8805f.json` | One-candidate site-screening run |
| `raw/pubchem-aspirin-search.json` | PubChem text-search response retained verbatim |
| `ui-smoke.json` | 11 routes, expected landmark, observed hash, error markers |
| `ui/*.png` | Production-build screenshots and defect/after-fix evidence |
| `DEFECTS.md` | Reproduced defects, root cause, fix and regression evidence |

## Automated result

- Backend: **821 passed, 0 failed, 0 errors, 0 skipped**, 383.6 s; JUnit retained.
- Frontend: **9 files / 27 tests passed**; `vue-tsc`, `vite build` and `ruff` passed.
- Production UI route smoke: **11/11 routes** found their expected landmark and
  no error marker; screenshots retained.

## Observed user flow

1. Workbench `一键准备 1iep 示例`.
2. Dock with real Vina: completed in **56.6 s**, **3 poses**, best
   **−13.25 kcal/mol**.
3. Result tabs: **参数 → 分析 → 结果**. Changing the receptor cleared the old
   result, pose and count and returned to Parameters.
4. Geometry check: **3/3 ✓**. RMSD vs reference: **0.37 Å** (best),
   **13.47 / 12.44 Å** (other poses); clusters **C1 / C2 / C3**.
5. Interactions: **57 contacts**; 2D map, table, residue filter and SVG
   export controls rendered.
6. Report: metrics, charts, IFP, Methods, CSV. Inspect-in-dock retained the
   historical job instead of silently using the current pipeline.
7. Batch: one prepared ligand completed; best **−13.28 kcal/mol**; CSV
   downloaded.
8. One-member virtual screening: completed in **11.99 s**, best
   **−13.261 kcal/mol**, ranking CSV retained.
9. One-candidate site screening: completed in **13.65 s**, best
   **−10.309 kcal/mol**.
10. PubChem text search for `aspirin` returned CID 2244, formula `C9H8O4`,
    `has3D=true`; no compound was downloaded into the workspace.
11. Catalog: `阿司匹林` alias search, detail preview, SMILES dialog; at 900 px
   the detail pane remains available as a bottom row.
12. Locale: Chinese ↔ English updates navigation and docking labels.

These are observations from one environment. Vina is stochastic and the
numbers are not acceptance constants.

## Reproduced defects

See [`DEFECTS.md`](DEFECTS.md). The fixes are **in the working tree**, not in
the published `v0.6.4` tag. Do not cite the release artifacts as containing
these fixes.

## Honest gaps

- No fresh 125-molecule screening run; a one-member screening run was executed.
- One site candidate was run; the full candidate set and ensemble run were not.
- No desktop/Qt native-dialog or QWebChannel run.
- One PubChem text search; ChEMBL and compound fetch were not run.
- Test machine uses SwiftShader; GPU rendering is not verified.

These gaps are represented as `partial` / `not-run` in
[`../MATRIX.md`](../MATRIX.md); they are not failures and are not claimed as
passes.
