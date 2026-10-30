# VinaStudio Functional Validation Protocol

**Scope:** user-facing software behaviour of VinaStudio 0.6.4.  
**Not a scientific accuracy claim.** Docking accuracy, 1IEP redocking and the
claim–evidence matrix live in [`docs/ACADEMIC_VALIDATION.md`](../../docs/ACADEMIC_VALIDATION.md)
and [`docs/VALIDATION.md`](../../docs/VALIDATION.md). A functional pass here
means an entry point behaved as documented; it does not mean a Vina score is a
binding free energy or that the program is accurate on unseen targets.

## 1. What this record is for

The project had automated tests and a manual checklist, but no single,
versioned record that answers:

1. which user-visible features were exercised in this run;
2. what input data and software versions produced the observations;
3. which observations were automated, which were manual, and which were not run;
4. where the raw output, screenshots and defect evidence live.

This directory is that record. The schema is deliberately conservative: a
missing or partial check stays `partial` / `not-run`; it is never promoted to
`pass` because the page rendered.

## 2. Evidence levels

| Level | Meaning |
|---|---|
| `automated` | Executed by pytest or Vitest in this record; raw result retained. |
| `ui-observed` | A real browser session was driven through the visible UI; screenshot retained. |
| `ui-route-only` | The route rendered its expected landmark; interaction not claimed. |
| `partial` | Some entry points or branches were exercised; named gaps remain. |
| `not-run` | Not executed in this environment; reason recorded. |

`ui-smoke.json` is route/landmark evidence only. The interaction walkthrough in
§5 is the evidence for the behaviour assertions. Both are needed.

## 3. Environment and provenance

The exact environment for the retained 2026-10-30 run is in
[`records/2026-10-30/environment.json`](records/2026-10-30/environment.json).
It records:

- application version and `git rev-parse HEAD`;
- dirty-tree status and the SHA-256 of the working-tree patch actually tested;
- Python, Node, pnpm, Vina, Meeko, RDKit, NumPy, SciPy, gemmi, platform and CPU;
- SHA-256 of the 1IEP receptor, ligand, crystal reference, crystal HETATM
  extract and validation manifest;
- the exact commands used.

The tested tree is **0.6.4 plus an uncommitted validation patch**; the released
tag remains `v0.6.4`. This is intentional: the record must describe what was
actually on disk, not relabel a dirty tree as the release commit.

### Reproduce

```bash
# dependencies and committed 1IEP data
uv sync --extra dev
pnpm -C web install
uv run python scripts/fetch_samples.py

# automated checks
uv run pytest -q --junitxml=validation/functional/records/2026-10-30/raw/pytest-junit.xml
pnpm -C web typecheck
pnpm -C web test
pnpm -C web build
uv run ruff check .

# production SPA, not the Vite dev server
uv run python scripts/build_web.py
uv run uvicorn vinastudio.server.app:create_app --factory \
  --host 127.0.0.1 --port 8760
uv run python validation/functional/ui_smoke.py \
  --base-url http://127.0.0.1:8760 \
  --out validation/functional/records/2026-10-30
```

`ui_smoke.py` requires `agent-browser` (`npm i -g agent-browser &&
agent-browser install`). It drives that CLI, not an in-repo browser dependency.
Without it, use the same route list manually; the route is not considered
verified by fetching HTML alone.

## 4. Feature matrix

The matrix is in [`MATRIX.md`](MATRIX.md) and machine-readable in
[`manifest.json`](manifest.json). Every router and every SPA route is assigned
to an area; areas with a named gap are marked `partial` or `not-run`.

## 5. User walkthrough (UI-observed)

The following path was executed against the production build and real Vina
backend on the committed 1IEP data. Values are observations, not expected
constants. Screenshots are in `records/2026-10-30/ui/`.

| ID | Step | Observed |
|---|---|---|
| U01 | Workbench → `一键准备 1iep 示例` | Receptor and ligand prepared; box entered the docking flow. |
| U02 | Dock → Start | Job completed; **56.6 s**, **3 poses**, best **−13.25 kcal/mol**. |
| U03 | Result tabs | Order is **参数 → 分析 → 结果**; result tab shows the pose table. |
| U04 | Change receptor in Parameters | Old result, poses, interactions and result count disappeared; page returned to Parameters. |
| U05 | Geometry check | Three pose rows showed **✓**; no error state. |
| U06 | Redocking RMSD | Best pose **0.37 Å**; later poses **13.47 / 12.44 Å** (not merged into a false success). |
| U07 | Cluster | Three clusters **C1 / C2 / C3**; representative navigation enabled. |
| U08 | Interactions | **57 contacts**; 2D map and residue list rendered; Export SVG available. |
| U09 | Report | Metrics, charts, IFP, Methods, CSV export and history loaded. |
| U10 | Report → Inspect in docking | Historical job stayed inspectable even though the current pipeline named another receptor. |
| U11 | Catalog | `阿司匹林` found via alias; 2D/3D detail rendered; SMILES dialog opens. |
| U12 | Catalog at 900 px | Detail pane remains reachable as a bottom row instead of disappearing. |
| U13 | Batch | One prepared ligand completed; best **−13.28 kcal/mol**; CSV downloaded. |
| U14 | Settings / locale | Chinese ↔ English updated navigation and docking labels. |
| U15 | UI routes | All 11 routes rendered their expected landmark; see `ui-smoke.json`. |
| U16 | Results search | Query `1iep` returned the expected completed run rows; see `ui/flow-results-search.png`. |
| U17 | Sketcher | Draw dialog and its template/import/undo controls rendered; see `ui/flow-sketcher.png`. |
| U18 | Screening | One-member library completed in **11.987 s**, best **−13.261 kcal/mol**, ranking CSV produced; see `raw/screening-b6bd0bc2b6aa.json`, `raw/screening-ranking.csv`. |
| U19 | Site screening | One candidate completed in **13.646 s**, best **−10.309 kcal/mol**; see `raw/site-fddb09c8805f.json`. |
| U20 | PubChem provider | Text search `aspirin` returned CID **2244**, formula `C9H8O4`, `has3D=true`; see record narrative. |
| U21 | Provider UI | Compound-search dialog → PubChem → `aspirin` rendered CID 2244 and a download action; see `completion/ui/flow-provider-ui.png`. |

### Defect evidence

Six real defects were found across the two phases and fixed in the tested
patches; details are in [`records/2026-10-30/DEFECTS.md`](records/2026-10-30/DEFECTS.md).

1. A report/history load leaked a historical job into Workbench as if it were
   the current pipeline result.
2. Historical interaction analysis used the **current** pipeline receptor, not
   the receptor recorded in the job.
3. Catalog hid the detail/prepare pane below 900 px.
4. Software-render desktop startup produced no WebGL context.
5. A historical cancelled run displayed 1500% progress.
6. Odd-voxel affinity-map requests returned a bare 500 instead of the
   `forceEvenVoxels` remedy.

## 6. Remaining boundaries and gaps

The following are either completed with a narrow scope, or not exercised:

- **Full 125-member virtual screening** completed in the completion phase:
  123 completed, 2 input failures (digoxin ETKDG, cisplatin multi-fragment);
  this is a workflow/scale check, not an accuracy claim.
- **Desktop-only paths** (Qt native file dialogs, QWebChannel bridge, cold-start
  with persistent HTTP cache) were not exercised; the desktop startup smoke
  after the SwiftShader fix is recorded.
- **Online compound providers**: PubChem search and ChEMBL search/fetch were
  exercised; the provider UI tab was not.
- **GPU rendering** was not exercised: the test machine used SwiftShader; the
  software-render warning is expected and is not counted as a functional pass
  or failure.
- **Site screening**: five candidate pockets were launched live; ensemble
  docking was not. Their contracts and automated tests are in the matrix.

## 7. Claims

Supported by this record:

- the listed user flows render and complete on the recorded environment;
- the automated suite passes for the recorded commit plus patch;
- the three recorded defects were reproduced and fixed;
- the exact inputs, versions, commands and screenshots are retained.

Not supported:

- general docking accuracy, enrichment or prospective screening performance;
- official PoseBusters compliance;
- cross-platform or GPU reproducibility;
- “all features pass” for any area marked `partial` or `not-run`.

## 8. 2026-10-30 completion phase

Second pass adds full 125-member screening (123/125 completed; two input
failures), five-pocket site screening, ChEMBL/PubChem, upload, project
persistence, affinity maps, results favorite filtering, sketcher import and
desktop software-render startup. See
[`records/2026-10-30/completion/README.md`](records/2026-10-30/completion/README.md).
