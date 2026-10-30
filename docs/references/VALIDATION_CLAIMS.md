# Validation claim → source ledger

This ledger is the review trail for the 0.6.4 academic validation report. It is
not a substitute for the report; it answers “which sentence is allowed to say
this, and what supports it?”.

| Claim in report | Source | Exact support / boundary |
|---|---|---|
| Vina is the docking engine; scores are model output, not experimental ΔG | Trott & Olson 2010 [1]; Eberhardt et al. 2021 [2] | engine and scoring description; report explicitly labels the affinity window local |
| Meeko performs PDBQT parameterisation | Santos-Martins et al. 2025 [3] | software method; no claim that Meeko validates binding |
| RDKit/ETKDG generates the 3D conformer used for input preparation | Riniker & Landrum 2015 [4] | method description only |
| 2 Å is a common redocking acceptance convention, not a physical constant | Bissantz et al. 2000 [5]; Kellenberger et al. 2004 [6] | comparative docking background; the exact gate remains a project choice |
| Geometry checks are a PoseBusters-style subset | Buttenschoen et al. 2024 [7] | inspiration for checks; thresholds and implementation are project-specific |
| 1IEP is c-Abl + imatinib and the crystal ligand is STI A 201 | Nagar et al. 2002 [8]; RCSB 1IEP [9] | structure identity and provenance |
| CASF-2016 is the kind of multi-target benchmark needed for a broad claim | Su et al. 2019 [10] | explicitly **not run** in this report |
| DUD-E is an enrichment benchmark, not used here | Mysinger et al. 2012 [11] | explicitly **not run** in this report |
| internal clash is heavy-atom only | VinaStudio implementation decision | project adaptation: PDBQT drops non-polar H; Meeko rebuilds H after docking. No published claim that reconstructed H geometry is collision evidence. |
| `reference_unmatched`/unverifiable reference fails | VinaStudio code + tests | `reference_matches_poses` must return true; otherwise the case fails |
| 1IEP reference is provenance-separated but coordinates equal input | generated report + SHA table | report explicitly says it is not a second experimental measurement |

The report uses 14 numbered references, all represented in `VinaStudio.bib` and
the README table. If a claim cannot be mapped to this table, it must be removed or
labelled as a limitation.

Additional operational claims:

| Claim in report | Source | Exact support / boundary |
|---|---|---|
| 2HYY is exploratory and not independent | manifest + generated report | reference path equals ligand path; harness records `independentFromLigand=false` and fails the case |
| CLI/API agreement is energy-level, not coordinate identity | `tests/integration/test_vina_cli_backend.py` | same pose count and per-pose energies within 0.01 kcal/mol; no coordinate comparison |
| 1IEP receptor preparation has 2702 atoms | `tests/integration/test_receptor_prep.py`, golden test | atom-count parity; per-atom charges drift within the test bounds, so this is not bit-identical |
| Vinardo and AutoDock4 are not evaluated | report §3.1 + no dataset/run | methods exist; no result is claimed |
