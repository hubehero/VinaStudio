# VinaStudio Academic Validation Report

**English** · [简体中文](ACADEMIC_VALIDATION.zh-CN.md) · [Home](../README.en.md)

**Report version:** 1.0  
**Software version:** 0.6.4 (development tree)  
**Report date:** 2026-10-29  
**Status:** reproducible software-validation report, not a peer-reviewed
benchmark paper.

> **One-sentence scope.** This report tests whether VinaStudio's preparation,
> docking, pose-recovery, geometry-check and reporting path is reproducible on
> the committed 1IEP redocking control; it does **not** estimate general docking
> accuracy, enrichment, or binding affinity.

## 1. Scope and explicit non-claims

### 1.1 What is validated

- the 1IEP redocking control, including an independent crystal-ligand reference
  extracted from the PDB HETATM record;
- preparation parity with the upstream AutoDock Vina tutorial data;
- fixed-frame, symmetry-aware heavy-atom RMSD against that crystal reference;
- the six project geometry checks and the failure/box guards;
- equivalence of the CLI and Python-API docking backends at a fixed protocol;
- the provenance captured by the validation report.

### 1.2 What is not claimed

This report does **not** claim:

- general accuracy on unseen targets, target classes, or chemical libraries;
- enrichment, ROC, AUC, EF1%, BEDROC, or prospective screening performance;
- that a Vina score is an experimental binding free energy;
- that the six checks are the official PoseBusters suite, or that a pass is a
  PoseBusters pass;
- that the 20 Å box is the biologically correct binding site;
- that two cases constitute a benchmark;
- that any result is portable across seeds, CPU counts, platforms, or software
  versions without re-running.

The evidence is deliberately narrow. A single successful redocking is a
**necessary control**, not sufficient evidence of general docking accuracy.

## 2. Research questions and evidence hierarchy

| ID | Question | Primary evidence | Claim strength |
|---|---|---|---|
| RQ1 | Does ligand/receptor preparation reproduce the documented upstream data? | byte-parity and atom-count tests | software parity |
| RQ2 | Does docking recover the crystal pose in the documented box? | fixed-frame RMSD + geometry report | one case |
| RQ3 | Do the CLI and API backends agree at fixed settings? | pose-count and per-pose energy equivalence test | backend equivalence |
| RQ4 | Do guards reject invalid boxes/references and bad poses? | unit/integration negative controls | failure detection |
| RQ5 | Is a run reproducible from the report? | commit/version/checksums/full parameters | provenance |

Evidence is ranked above prose. If a statement is not backed by a test, a
generated report field, or a cited source, it is marked as a limitation.

## 3. Software and methods

### 3.1 Docking engine

VinaStudio 0.6.4 drives **AutoDock Vina 1.2.7** through either the Python API
or the official command-line binary. The report records which backend was used;
the two are the same engine, not two scoring methods. The Vina scoring function
and search procedure are described by Trott & Olson [1]; the 1.2.x API and force
field changes are described by Eberhardt et al. [2].

The default protocol is not a claim that these are universally optimal values.
The values used for this report are in §5.

VinaStudio also exposes Vinardo [14] and AutoDock4 [13] scoring; neither is evaluated in this report.

### 3.2 Ligand and receptor preparation

Meeko performs ligand parameterisation and PDBQT writing [3]. RDKit performs
molecular parsing, hydrogen handling and ETKDG conformer generation [4].
Preparation is a deterministic software transformation only when the input,
software versions, and options are fixed; it is not an experimental
measurement.

1IEP ligand preparation is compared with the upstream tutorial PDBQT after
normalising the charge-column sign convention. Receptor preparation is checked
for the documented 2702-atom count and element composition. The known
Met/Cys sulfur type difference is recorded rather than hidden.

### 3.3 RMSD definition

The pose RMSD is the **heavy-atom, symmetry-aware, fixed-frame** RMSD returned
by `rdMolAlign.CalcRMS` on the prepared pose and the crystal reference. It does
**not** perform a rigid-body superposition first. Superimposing first would turn
a pose translated to another pocket into an artificial ~0 Å result and would
destroy the meaning of redocking.

The 2.0 Å acceptance threshold is used here as a project software gate, not a
physical constant. Comparative docking evaluations discuss RMSD success criteria
and threshold sensitivity [5,6]; the exact gate remains a project choice and is
reported explicitly.

### 3.4 Geometry checks

The harness applies six project checks:

| Check | Operational definition | Severity |
|---|---|---|
| `internal_clash` | non-bonded heavy-atom pair closer than 0.65 × (vdW_i + vdW_j) | error for any pair with topological separation ≥ 4; warning only for rotatable 1–4 pairs |
| `bond_length_outlier` | pose/reference bond-length difference > 0.45 Å | error |
| `angle_outlier` | pose/reference angle difference > 25° | error |
| `planarity_break` | aromatic/double-bond plane RMSD > 0.1 Å | error |
| `chirality_flip` | CIP label differs from the reference | error |
| `out_of_box` | atom more than 2.0 Å outside the box | error |

These are a **PoseBusters-style subset** inspired by the published checks [7],
not the official suite. The thresholds are project constants in
`vinastudio/core/chem/pose_validation.py`; they are not claimed to be
PoseBusters thresholds.

**Hydrogen handling:** `internal_clash` is heavy-atom only. PDBQT omits
non-polar hydrogens, and Meeko reconstructs hydrogens after docking; those
positions are not evidence of a steric clash. Including them rejected valid
heavy-atom 1IEP poses on H–H distances (three non-best poses in the pre-0.6.4
run), so the check deliberately evaluates the authoritative heavy-atom geometry.
This is an explicit adaptation, not a claim that all hydrogen geometry is
irrelevant.

### 3.5 Box and reference guards

A box with no receptor atom is rejected before docking; Vina otherwise returns
a page of 0.0 kcal/mol poses that can look like success. This guard is a
coordinate-frame sanity check, not evidence that the box is the correct binding
site.

The reference must be a separate file from the docking ligand and must match the
docked molecule by canonical heavy-atom SMILES. An unverifiable reference fails
the case; reference-relative RMSD is not reported as a pass when identity is
unknown.

## 4. Data provenance

### 4.1 Strict case: 1IEP

| Item | Value |
|---|---|
| PDB entry | 1IEP, c-Abl kinase domain + imatinib (STI-571) [8,9] |
| Receptor input | `vinastudio/resources/sample/1iep/1iep_receptorH.pdb` |
| Docking ligand | `vinastudio/resources/sample/1iep/1iep_ligand.sdf` |
| Crystal reference | `vinastudio/resources/sample/1iep/1iep_reference.sdf` |
| Crystal HETATM extract | `vinastudio/resources/sample/1iep/1iep_crystal_ligand.pdb` |
| Reference source | RCSB 1IEP `HETATM STI A 201` **coordinates**, applied to the tutorial ligand graph/bond orders and +1 charge; `CONECT` retained for provenance |
| Reference heavy atoms | 37 |
| Ligand atoms (including H) | 69; 37 heavy |
| Reference/ligand canonical SMILES | identical |
| Max heavy-atom coordinate difference | 0.000 Å |
| RCSB 1IEP full-PDB SHA-256 | `577386b4b8bc58a570facba0c8a843386842caef5ed7b60106c685d0f68d4218` |

The upstream tutorial SDF and the PDB crystal ligand have the same heavy-atom
coordinates. The improvement here is **coordinate-provenance separation**: the
reference coordinates are taken from the PDB HETATM record instead of comparing
the input file with itself. It is still the same deposited structure, and its
bond orders, tautomer and +1 charge are inherited from the tutorial SDF, so it is
not a chemistry-independent or a second experimental measurement. This
distinction is stated so the result is not over-sold.

SHA-256 values recorded by the harness:

| File | SHA-256 |
|---|---|
| `1iep_receptorH.pdb` | `5f6aee6029f9a2a2c2be32d4eb948ae70808690573e1b69a0850cdffd7048ca7` |
| `1iep_ligand.sdf` | `051b8742c32adc05c07fb486a4e7c9327f84e131cee33ac4e6a568d07553eb38` |
| `1iep_reference.sdf` | `1bcc3920c107e60300fb7ac7fbe4d332c0ae2eb9b75baf2f7b7978f124343700` |
| `1iep_crystal_ligand.pdb` | `8ad50e10d641f5ad3fcdbeb2ad409d1af9850eedd95484b33f9608630cc066bd` |

### 4.2 Optional case: 2HYY

2HYY [12] is a local, gitignored sample in the separate
`validation/manifest.optional-2hyy.json` manifest. It is reported only as a
self-referenced exploratory case and is **not** evidence or part of the committed
core. Its receptor preparation excludes 62
template-unmatched residues and defaults unresolved histidines to HIE; both
warnings are retained with the result. A pass with those warnings does not mean
the omitted residues are irrelevant.

### 4.3 Data not used

No PDBbind, CASF, DUD-E, PoseBusters test set, or decoy library was downloaded,
redistributed, or evaluated in this increment. CASF-2016 [10] and DUD-E [11] are
listed only to make the missing benchmark scope explicit.

## 5. Protocol

Environment recorded by the report generator:

| Item | Value |
|---|---|
| App version | 0.6.4 |
| Python | 3.12.14 |
| Platform | Linux x86_64 |
| Vina | 1.2.7 |
| Meeko | 0.8.0 |
| RDKit | 2026.9.1 |
| NumPy | 2.5.4 |
| SciPy | 1.18.1 |
| gemmi | 0.7.5 |
| Engine backend | `vina` Python API |
| CPU count | 8 |
| Git commit | recorded by the report; the draft run was generated from a dirty working tree |

The 1IEP protocol:

| Parameter | Value |
|---|---|
| Box centre (Å) | `(15.190, 53.903, 16.917)` |
| Box size (Å) | `(20, 20, 20)` |
| Grid spacing (Å) | 0.375 |
| Scoring | `vina` |
| Exhaustiveness | 8 (sensitivity: 4 and 32) |
| Requested poses | 9 |
| Seed | 42 |
| Energy range (kcal/mol) | 3.0 |
| Minimum RMSD (Å) | 1.0 |
| Max evaluations | 0 (Vina heuristic) |
| CPU | 0 (all available; report records 8 logical CPUs) |
| Refinement | enabled |
| `allowBadResidues` | false |
| RMSD threshold | 2.0 Å |
| Affinity range | −14.5 to −11.0 kcal/mol |

The affinity range is a local acceptance window, not a published constant.

## 6. Results

### 6.1 1IEP redocking

Command:

```bash
uv run python scripts/validate_benchmark.py --case 1iep \
  --out-dir validation-output
```

Observed result:

| Metric | Value |
|---|---:|
| Status | passed |
| Top-ranked affinity (kcal/mol) | −13.286 |
| Top-ranked fixed-frame RMSD (Å) | 0.353 |
| Poses returned | 5 |
| Geometry errors (all poses) | 0 |
| Geometry warnings | 0 |
| Receptor atoms | 2702 |
| Ligand atoms (PDBQT) | 40 |
| Reference match | true |
| Reference independent path | true |

The geometry count is zero under the documented heavy-atom `internal_clash`
check. Before that adaptation, three non-best poses showed H–H distances below
the clash threshold; those were reconstructed-hydrogen artifacts, not
heavy-atom pose failures.

The top-ranked pose moves the crystal reference by 0.353 Å without
superposition. The older 0.260 Å prose value predates the 0.6.3 change from
superimposed `GetBestRMS` to fixed-frame `CalcRMS`; it is not directly comparable
and is superseded by this report.

### 6.2 Exhaustiveness sensitivity

Same seed and box; only exhaustiveness changed:

| Exhaustiveness | Top-ranked affinity (kcal/mol) | Top-ranked RMSD (Å) | Poses | Errors | Observed elapsed |
|---:|---:|---:|---:|---:|---:|
| 4 | −13.286 | 0.353 | 3 | 0 | 18.3 s |
| 8 | −13.286 | 0.353 | 5 | 0 | 28.9 s |
| 32 | −13.251 | 0.360 | 6 | 0 | 173.2 s |

This is a descriptive sensitivity check, not a converged sampling study. The
timings come from dedicated sensitivity runs and are not the headline run's
elapsed time. It shows that the pose-recovery conclusion is stable across these
three settings for this case; it does not establish convergence for other systems.

### 6.3 Preparation parity

The existing integration checks pass:

- ligand preparation reproduces the upstream PDBQT after documented charge-sign
  normalisation;
- receptor preparation gives 2702 atoms with the documented element counts;
- the accepted atom-type difference is Met/Cys `S` versus upstream `SA`;
  per-atom charges are not bit-identical (bounded below).

These are software-parity checks, not new docking results. Receptor atom types
agree, but per-atom charges are not bit-identical: the existing test permits a
mean absolute drift below 0.03 e, a maximum below 0.75 e, and 430 atoms shifted
by more than 0.05 e. Charges enter the Vina score, so this is a scoring-relevant
approximation, not a cosmetic label.

### 6.4 CLI/API equivalence

`tests/integration/test_vina_cli_backend.py` passes **9/9** tests, including
identical pose counts and per-pose energies within 0.01 kcal/mol at fixed
seed/exhaustiveness, plus the result contract. It does not compare coordinates;
the wording here says energy-level agreement, not pose-for-pose geometric
identity. The two backends share Vina 1.2.7.

### 6.5 Negative controls and guards

The test suite covers:

- a box entirely outside the receptor is rejected;
- non-bonded heavy-atom clashes, bond-length/angle outliers, planarity breaks,
  chirality flips and out-of-box poses produce findings;
- a missing optional case is `skipped`, never counted as passed;
- an unmatched/unverifiable reference fails the case;

These controls support failure detection, not accuracy.

### 6.6 Optional 2HYY

Command:

```bash
uv run python scripts/validate_benchmark.py \
  --manifest validation/manifest.optional-2hyy.json \
  --case 2hyy --out-dir validation-output
```

Local exploratory run (not part of the committed core):

| Metric | Value |
|---|---:|
| Status | failed (self-referenced; not evidence) |
| Exploratory affinity (kcal/mol) | −12.611 |
| Self-referenced RMSD (Å) | 1.117 |
| Poses | 1 |
| Geometry errors | 0 |
| Receptor atoms | 9673 |
| Ligand atoms | 39 |
| Warnings | 62 residues excluded; unresolved histidines defaulted to HIE |

The run is **not** a validation pass: its reference is the docking ligand file
itself. It is reported only to show why a self-referenced case is rejected. The
62-residue warning is retained, and the result does not broaden the claim beyond
1IEP. The harness now records `independentFromLigand=false` and fails such a case.

## 7. Statistical treatment

Only descriptive statistics are reported: one protocol per case, five poses for
the primary run, and a three-point exhaustiveness sensitivity table. No
confidence interval, p-value, bootstrap, rank correlation, enrichment factor or
multiple-comparison correction is presented because the design does not support
them. With n = 1 primary system (and n = 1 optional local system), an inferential
statistic would create false precision.

The correct next step for a quantitative benchmark is a pre-registered,
licensed, multi-target dataset with held-out systems, multiple seeds, and an
explicit enrichment/ranking endpoint; CASF-2016 [10] or DUD-E [11] are examples
of that scope, not claims made here.

## 8. Discussion

The result supports a narrow conclusion: on the committed 1IEP control, using
the documented box and protocol, VinaStudio prepares the inputs, docks, exports
poses, and identifies a near-crystal pose. It also supports the claim that the
CLI and API doors agree under the tested protocol and that known-bad inputs are
rejected rather than silently accepted.

It does not support a general accuracy statement. Redocking one kinase with its
crystallographic ligand is a sanity check, not a blind benchmark. The box is
derived from the known binding site, the ligand is the crystal ligand, and no
decoys or alternative targets are included. A reviewer should treat the pass as
evidence of a working pipeline and a reproducible control, not as evidence that
VinaStudio will reproduce arbitrary ligands.

## 9. Threats to validity

1. **Single system / single target family.** 1IEP is c-Abl + imatinib; no
   scaffold or target diversity.
2. **Known-site box.** The box is centred on the crystal ligand; this is not a
   blind pocket search.
3. **Reference provenance.** The reference coordinates are PDB-derived but
   identical to the upstream input SDF; bond orders, tautomer and the +1 charge
   also come from that SDF. It is coordinate-provenance-separated, not
   chemistry-independent and not a second experimental measurement.
4. **Stochastic search.** Vina's search is stochastic; seed 42 makes this run
   reproducible, not the method deterministic.
5. **One run per setting.** The sensitivity table has three exhaustiveness
   values but not repeated seeds or repeats.
6. **Geometry checks are a subset.** They are not official PoseBusters and have
   not been validated against the official tool on a labelled set.
7. **Reconstructed hydrogens.** `internal_clash` is heavy-atom only; C–H and
   hydrogen geometry still need scrutiny, and the hydrogen treatment is a
   documented approximation.
8. **Optional 2HYY is self-referenced.** Its reference is the ligand file itself,
   so the harness fails it; 62 excluded residues and HIE defaults add further
   caveats. It is not a confirmation.
9. **Affinity window.** The acceptance range was chosen for this control and is
   not a universal threshold.
10. **No benchmark data.** No PDBbind/CASF/DUD-E/PoseBusters dataset was run;
    no enrichment or ranking claim is possible.

## 10. Reproduction

```bash
# install and fetch the committed gold standard
uv sync --extra dev
uv run python scripts/fetch_samples.py
uv run python scripts/fetch_vina_cli.py   # needed for the CLI/API parity tests

# build the independent crystal reference from a full 1IEP PDB
# (the committed reference is already present; this regenerates it)
uv run python scripts/build_1iep_reference.py \
  --pdb vinastudio/resources/sample/1iep/1iep.pdb \
  --ligand vinastudio/resources/sample/1iep/1iep_ligand.sdf

# primary validation report (JSON + Markdown + per-case artifacts)
uv run python scripts/validate_benchmark.py --case 1iep \
  --out-dir validation-output

# complete test and interface gates
uv run pytest -q
uv run ruff check .
pnpm -C web typecheck
pnpm -C web test
pnpm -C web build
```

Generated artifacts are under `validation-output/` and are intentionally
gitignored. The JSON report is schema `2.0` and contains the environment,
checksums, reference independence, full docking parameters and per-case
provenance.

## 11. Claim-evidence matrix

| Claim | Evidence | Result |
|---|---|---|
| 1IEP ligand preparation matches upstream after charge normalization | `tests/integration/test_ligand_prep.py` | pass |
| 1IEP receptor has 2702 atoms and documented element counts | `tests/integration/test_receptor_prep.py`, golden test | pass |
| Top-ranked pose is within 2 Å of the PDB-coordinate reference | generated `validation-report.json` | 0.353 Å |
| Poses satisfy the six project checks | generated report | 0 errors, 0 warnings |
| CLI and API agree at fixed protocol | `tests/integration/test_vina_cli_backend.py` | 9/9 pass |
| Invalid box is rejected | `tests/unit/test_box.py`, `tests/integration/test_docking_api.py` | pass |
| Missing optional case is skipped, not passed | `tests/unit/test_validation.py` | pass |
| Reference graph is consistent with the docked ligand | harness provenance + `reference_matches_poses` | true (both derive from the tutorial SDF) |
| No enrichment/accuracy claim is made | this report + no dataset run | explicit non-claim |

## 12. References

Claim-to-source trace: [`docs/references/VALIDATION_CLAIMS.md`](references/VALIDATION_CLAIMS.md).

Metadata assembled and checked against Crossref on 2026-10-29; PDB entries
checked against RCSB. Full BibTeX: [`docs/references/VinaStudio.bib`](references/VinaStudio.bib).
Access/licence notes: [`docs/references/README.md`](references/README.md).
Full text is reached through the DOI/publisher link; only open-access PDFs whose
licences permit redistribution are included in this repository.

1. **Trott, O.; Olson, A. J.** AutoDock Vina: Improving the speed and accuracy of docking with a new scoring function, efficient optimization, and multithreading. *Journal of Computational Chemistry* **2010**, 31(2), 455–461. doi:[10.1002/jcc.21334](https://doi.org/10.1002/jcc.21334).
2. **Eberhardt, J.; Santos-Martins, D.; Tillack, A. F.; Forli, S.** AutoDock Vina 1.2.0: New Docking Methods, Expanded Force Field, and Python Bindings. *Journal of Chemical Information and Modeling* **2021**, 61(8), 3891–3898. doi:[10.1021/acs.jcim.1c00203](https://doi.org/10.1021/acs.jcim.1c00203).
3. **Santos-Martins, D.; He, Y.; Eberhardt, J.; Sharma, P.; Bruciaferri, N.; Holcomb, M.; Llanos, M. A.; Hansel-Harris, A.; Barkdull, A. P.; Tillack, A. F.; Bianco, G.; Paulsen, M.-L.; Mato, J.; Taneja, I.; Forli, S.** Meeko: Molecule Parametrization and Software Interoperability for Docking and Beyond. *Journal of Chemical Information and Modeling* **2025**, 65(24), 13045–13050. doi:[10.1021/acs.jcim.5c02271](https://doi.org/10.1021/acs.jcim.5c02271).
4. **Riniker, S.; Landrum, G. A.** Better Informed Distance Geometry: Using What We Know To Improve Conformation Generation. *Journal of Chemical Information and Modeling* **2015**, 55(12), 2562–2574. doi:[10.1021/acs.jcim.5b00654](https://doi.org/10.1021/acs.jcim.5b00654).
5. **Bissantz, C.; Folkers, G.; Rognan, D.** Protein-Based Virtual Screening of Chemical Databases. 1. Evaluation of Different Docking/Scoring Combinations. *Journal of Medicinal Chemistry* **2000**, 43(25), 4759–4767. doi:[10.1021/jm001044l](https://doi.org/10.1021/jm001044l).
6. **Kellenberger, E.; Rodrigo, J.; Muller, P.; Rognan, D.** Comparative evaluation of eight docking tools for docking and virtual screening accuracy. *Proteins: Structure, Function, and Bioinformatics* **2004**, 57(2), 225–242. doi:[10.1002/prot.20149](https://doi.org/10.1002/prot.20149).
7. **Buttenschoen, M.; Morris, G. M.; Deane, C. M.** PoseBusters: AI-based docking methods fail to generate physically valid poses or generalise to novel sequences. *Chemical Science* **2024**, 15(9), 3130–3139. doi:[10.1039/D3SC04185A](https://doi.org/10.1039/D3SC04185A). Open access, CC BY.
8. **Nagar, B.; Bornmann, W. G.; Pellicena, P.; Schindler, T.; Veach, D. R.; Miller, W. T.; Clarkson, B.; Kuriyan, J.** Crystal structures of the kinase domain of c-Abl in complex with the small molecule inhibitors PD173955 and imatinib (STI-571). *Cancer Research* **2002**, 62(15), 4236–4243. PMID: [12154025](https://pubmed.ncbi.nlm.nih.gov/12154025/).
9. **RCSB Protein Data Bank.** 1IEP: c-Abl kinase domain in complex with imatinib (STI-571). doi:[10.2210/pdb1IEP/pdb](https://doi.org/10.2210/pdb1IEP/pdb); [structure page](https://www.rcsb.org/structure/1IEP).
10. **Su, M.; Yang, Q.; Du, Y.; Feng, G.; Liu, Z.; Li, Y.; Wang, R.** Comparative Assessment of Scoring Functions: The CASF-2016 Update. *Journal of Chemical Information and Modeling* **2019**, 59(2), 895–913. doi:[10.1021/acs.jcim.8b00545](https://doi.org/10.1021/acs.jcim.8b00545). Not used here; benchmark scope only.

11. **Mysinger, M. M.; Carchia, M.; Irwin, J. J.; Shoichet, B. K.** Directory of Useful Decoys, Enhanced (DUD-E): Better Ligands and Decoys for Better Benchmarking. *Journal of Medicinal Chemistry* **2012**, 55(14), 6582–6594. doi:[10.1021/jm300687e](https://doi.org/10.1021/jm300687e). Not used here; future enrichment scope only.
12. **RCSB Protein Data Bank.** 2HYY: c-Abl kinase domain in complex with imatinib. doi:[10.2210/pdb2HYY/pdb](https://doi.org/10.2210/pdb2HYY/pdb); [structure page](https://www.rcsb.org/structure/2HYY). Optional local input, not part of the committed core evidence.

13. **Morris, G. M.; Huey, R.; Lindstrom, W.; Sanner, M. F.; Belew, R. K.; Goodsell, D. S.; Olson, A. J.** AutoDock4 and AutoDockTools4: Automated docking with selective receptor flexibility. *Journal of Computational Chemistry* **2009**, 30(16), 2785–2791. doi:[10.1002/jcc.21256](https://doi.org/10.1002/jcc.21256). Not evaluated here.
14. **Quiroga, R.; Villarreal, M. A.** Vinardo: A Scoring Function Based on AutoDock Vina Improves Scoring, Docking, and Virtual Screening. *PLOS ONE* **2016**, 11(5), e0155183. doi:[10.1371/journal.pone.0155183](https://doi.org/10.1371/journal.pone.0155183). Open access, CC BY 4.0; not evaluated here.

## 13. Report history

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-10-29 | Initial 0.6.4 report; independent 1IEP reference; provenance schema; heavy-atom clash check. |
