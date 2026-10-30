# Functional validation — completion phase (same 2026-10-30 record)

This phase extends the committed dossier without rewriting its original evidence.
It exercised the remaining user-facing workflows at their real scale where
practical. The release tag remains `v0.6.4`; the tests ran on `2c52ed9` plus
`working-tree.patch` in this directory.

## Automated checks

| Check | Result |
|---|---|
| Backend pytest | **830 passed, 0 failed, 0 errors, 0 skipped**, 370.0 s (includes the diagnostics suite) |
| Frontend Vitest | **9 files / 27 tests passed** |
| `vue-tsc` | passed |
| `vite build` | passed |
| UI route smoke | **11/11** routes found their landmark |

## Live workflows added

| ID | Workflow | Observed |
|---|---|---|
| C01 | Full built-in library screening | **125 requested / 123 completed / 2 failed**, 559.474 s, best **−12.985 kcal/mol** |
| C02 | Full five-pocket site screening | 5 candidates, **5 completed**, 66.338 s, best **−9.541 kcal/mol** |
| C03 | ChEMBL provider | text search returned imatinib `CHEMBL941`; fetch wrote `chembl-chembl941_1.sdf`, `has3D=false` |
| C04 | PubChem provider | text search returned aspirin CID 2244, `has3D=true` |
| C05 | File upload | uploaded 1IEP SDF through `/api/files/upload`; detect returned `ligand`/`extension` |
| C06 | Project persistence | save → load format **1.1** → list → delete; no warnings |
| C07 | Affinity maps | odd box returns **422** with `forceEvenVoxels` remedy; even box wrote 22 maps |
| C08 | Results search | favorite toggle + “favorites only” filter returned the marked run |
| C09 | Sketcher | SMILES import, structure display, cleanup enabled; canceled without adding |
| C10 | Desktop software fallback | desktop app starts API/WebSocket; no 3Dmol error after the ANGLE fix |
| C11 | Provider UI | Compound dialog → PubChem → aspirin CID 2244 and download action |
| C12 | Diagnostics and safe repair | 11 checks (10 server + WebGL); safe directory repair; corrupt config/catalog/job index left untouched |

The two full-library failures are retained, not hidden:

- `digoxin` — `could not generate 3D coordinates with ETKDGv3`
- `cisplatin` — SDF contains multiple disconnected fragments

These are input/preparation failures, not a claim that the other 123 are
scientifically correct.

## Defects reproduced and fixed in this phase

### D04 — software-render desktop had no WebGL

Pre-fix log `raw/desktop-startup.log` shows `--disable-gpu` followed by
`Cannot read properties of null` and failure to create the 3Dmol viewer.
`vinastudio/desktop/env.py` now asks ANGLE for SwiftShader
(`--enable-unsafe-swiftshader --use-gl=angle --use-angle=swiftshader`);
`raw/desktop-startup-angle.log` starts without that error.

### D05 — historical screening progress displayed 1500%

Pre-fix: `ui/defect-screening-1500.png`. `ScreeningView.vue` now clamps display
to 0–100 without rewriting the stored historical value. After reload:
`ui/screening-progress-clamped.png`.

### D06 — odd-voxel map request was a 500

Pre-fix response was a bare Vina `RuntimeError` (500). The endpoint now builds
the same `Box` model as the UI and returns a 422 naming `forceEvenVoxels`.
Evidence: `raw/write-maps-odd-response.txt`; regression is in
`tests/integration/test_box_api.py`.

## Remaining gaps (not passed claims)

- Desktop native file dialogs and QWebChannel interaction were not driven.
- ChEMBL/PubChem **UI tab** was not driven; API provider calls were.
- GPU hardware rendering was not available; SwiftShader path only.
- Full-library screening is not an accuracy/benchmark result and has 2 known
  input failures.
- The full screening run used exhaustion 1, a scale/correctness smoke; it is
  not the 1IEP redocking protocol.

## Files

`environment.json`, `working-tree.patch`, `SHA256SUMS`, `raw/` and `ui/` are
self-contained evidence for this phase. `raw/full-screening-ranking.csv` is the
default top-100 export; `raw/full-screening-ranking-top200.csv` contains all
123 completed rows.
