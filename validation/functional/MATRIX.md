# Functional Matrix — 0.6.4 validation tree

Status definitions are in [`README.md`](README.md) §2. `partial` and `not-run`
are deliberate, not failures hidden behind a green check.

| ID | Functional area | User entry | Automated evidence | UI evidence | Status | Named gap |
|---|---|---|---|---|---|---|
| F01 | Workbench pipeline | `/workbench`, one-click 1iep | golden pipeline test | `ui/workbench.png`; U01 | **pass** | — |
| F02 | Catalog, studies, collections, libraries, selections, PDB library | `/molecules` | `test_catalog_api.py`, `test_library_api.py`, `test_catalog_core.py`, `test_catalog_migrate.py` | `ui/molecules.png`; U11–U12 | **pass** | — |
| F03 | File ingest: filters, upload, detect, renderable, samples | `/molecules` upload/drop | `test_detect_api.py`, `test_preparation_api.py`, `test_renderable_api.py`, `test_origin_guard.py` | file dialog opened; upload bytes not driven | **partial** | native file picker / drag-drop not fully driven |
| F04 | Ligand preparation + SMILES | Catalog and Molecule flows | `test_ligand_prep.py`, `test_preparation_api.py`, `test_sketch_api.py` | SMILES dialog; 3D detail | **pass** | — |
| F05 | Receptor preparation, flexible residues, mmCIF | Catalog / prep dialog | `test_receptor_prep.py`, `test_preparation_api.py`, `test_detect_api.py` | receptor 1iep cut-out | **partial** | flexible-sidechain and mmCIF dialogs not live-driven |
| F06 | Box: metrics, autobox, pockets, config, maps | `/box` | `test_box_api.py`, `test_box.py`, `test_pocket_api.py`, `test_interactive_maps.py` | `ui/box.png`; `completion/raw/write-maps-*`, `pockets-5.json` | **partial** | maps API verified, but Box UI has no map-write action by design |
| F07 | Single docking, scoring, optimize, randomize, ensemble | `/docking` | `test_docking_api.py`, `test_docking_weights.py`, `test_ensemble_worker.py`, `test_golden_pipeline.py` | U02–U04; `ui/docking.png` | **pass** | ensemble not live-driven |
| F08 | Pose validation, RMSD, clustering, IFP, interactions | Dock Analysis / Results | `test_pose_validation.py`, `test_rmsd.py`, `test_cluster.py`, `test_ifp_contract.py`, `test_ifp_api.py`, `test_interactions_api.py` | U05–U08; `ui/flow-history-interactions.png` | **pass** | — |
| F09 | Export CSV / pose / bundle / import / 2D SVG | Dock Results / Report | `test_export.py`, `test_batch_export.py`, `test_report_svg_safety.py` | CSV and ZIP downloads; `ui/docking.png` | **pass** | 2D SVG download not separately opened here |
| F10 | Batch docking / progress / ranking / CSV | `/batch` | `test_batch_parallel.py`, `test_batch_molecules.py` | U13; `ui/flow-batch-complete.png` | **pass** | one-ligand smoke; full multi-ligand run not repeated |
| F11 | Virtual screening: import, run, cancel, resume, ranking, export | `/screening` | `test_screening_api.py`, `test_library_api.py` | full 125 run: `completion/ui/full-screening.png`, `raw/full-screening-*` | **pass** | 123/125 completed, 2 input failures recorded; no accuracy claim |
| F12 | Site screening: pockets → candidates → run/ranking | Box / Dock | `test_sites_api.py`, `test_site_screening_vina.py`, `test_pocket_api.py` | 5 candidates: `completion/raw/site-bb5cc99255b3-result.json` | **pass** | five-pocket live run; one-ligand candidate ranking |
| F13 | Results search: search, tags, favorite, bulk, views, compare, IFP grouping | `/results` | `test_results_api.py`, `test_results_db.py` | `ui/results.png`; U16 `ui/flow-results-search.png` | **partial** | favorite/tag/bulk/compare not individually driven |
| F14 | Project save/load/list/delete, format 1.1, workspace lifecycle, molecule manifest | top bar / Settings | `test_project_api.py`, `test_workspace_api.py`, `test_workspace.py`, `test_molecules_api.py` | Settings dialog loads | **partial** | native Save As / workspace migration not live-driven |
| F15 | Sketcher: analyze, cleanup, layout, templates | Catalog → Draw | `test_sketch_api.py`, `test_sketch_chem.py` | U17 `ui/flow-sketcher.png` | **partial** | drawing/cleanup canvas interaction not driven |
| F16 | System: health, info, selfcheck, capabilities, citation, upload limit, update check | `/environment`, Help | `test_system_api.py`, `test_system_selfcheck.py`, `test_system_update.py` | `ui/environment.png` | **pass** | — |
| F17 | Security: origin guard, upload header, path containment | API boundary | `test_origin_guard.py`, `test_origin.py`, `test_app_middleware.py`, `test_project_api.py` | not applicable | **pass** | no penetration-test claim |
| F18 | UI routes, settings, i18n, responsive dock/catalog, WebSocket status | all 11 routes | Vitest 27; typecheck/build | `ui-smoke.json`; `ui/flow-catalog-narrow-detail.png`; language switch | **pass** | desktop native bridge / GPU not covered |
| F20 | Desktop shell: Qt startup, software-render fallback, native dialogs, QWebChannel | packaged app | `test_desktop_env.py`, packaging tests | desktop startup logs; no native dialog run | **partial** | startup smoke only; native dialogs/QWebChannel not driven |
| F19 | Online compound providers (PubChem/ChEMBL) | Catalog library | `test_library_compounds_api.py`, `test_compound_sources.py` | U21; `completion/raw/chembl-*`, `completion/ui/flow-provider-ui.png` | **partial** | PubChem UI/API and ChEMBL API verified; ChEMBL UI/structure download not driven |

## Coverage accounting

- Automated: one command covers every router listed above; the retained JUnit
  XML is authoritative for node-level pass/fail.
- UI: 11 routes are route-smoke verified; 15 numbered user steps (U01–U15)
  are interaction-observed and screenshot-backed.
- **No claim is made that every field, error path or native menu was exercised.**
  The matrix names the gaps.
