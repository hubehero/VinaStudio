# Confirmatory Open Benchmark Protocol (v1)

**Status:** pre-registered before confirmatory docking results  
**Dataset:** `open-posebusters-v1`  
**Data:** PDB (CC0 1.0) + PoseBusters target pool (MIT); no restricted data  
**Pilot:** v1/v2 records are exploratory and excluded from the primary result

## 1. Question

On a pre-registered set of 12 open PDB/PoseBusters redocking targets, using one
fixed VinaStudio/Vina protocol, how often does the top-ranked pose recover the
native ligand within 2.0 Å, and what is the run-to-run spread across five seeds?

This is a redocking result for these targets, not a universal accuracy claim,
an affinity prediction, or an enrichment claim.

## 2. Target pool and exclusions

- Pool: the public PoseBusters benchmark list.
- Excluded pilot IDs: `5SB2`, `5SD5`, `5SIS`, `6M2B`.
- Excluded by eligibility rule:
  - covalent ligand (`LINK`/explicit covalent bond to the ligand);
  - peptide or clearly peptidomimetic ligand;
  - ligand heavy atoms outside 8–40;
  - PDB resolution > 2.5 Å;
  - no unambiguous non-water ligand HETATM;
  - obsolete or missing PDB entry.
- Selection: deterministic SHA-256 ranking with selection seed `20261102`,
  applying a maximum of two targets per target family.
- The resulting 12 IDs are frozen in `manifests/open-posebusters-v1.json`
  before any docking result exists.

## 3. Inputs

- Receptor: RCSB PDB entry.
- Ligand input: RCSB Chemical Component Dictionary `*_ideal.sdf`.
- Reference: PDB native-ligand HETATM coordinates copied onto the CCD graph by
  `scripts/build_benchmark_reference.py`; reference and input are separate files.
- Reference bond-length sanity is checked; implausible references fail.
- No predicted pocket is used.

## 4. Uniform preparation rule

For every target:

1. `defaultAltloc = "A"`; Meeko template mismatches are allowed to exclude
   only the named residues, and every exclusion is recorded.
2. Delete waters and the pre-registered cryoprotectant/buffer list.
3. Keep non-water HETATM groups within 6.0 Å of any native-ligand heavy atom.
4. Delete other non-water HETATM groups, recording them.
5. Record all kept/deleted groups and any residue lacking altloc A.
6. Box: native-ligand heavy-atom centroid, 22 Å cube, even voxels where required.
7. Vina scoring, exhaustiveness 8, 9 poses.

No target-specific box, cofactor list, threshold or seed override is permitted.

## 5. Seeds

Docking seeds: `42,43,44,45,46` for every target. That is 12 × 5 = 60
case/seed runs. Each run gets its own artifact directory.

## 6. Geometry and official PoseBusters

The project's six geometry checks are recorded as before. Separately, official
PoseBusters is run on every primary pose. Its version is recorded. If it cannot
be installed or run, the field is `not-run` with a reason; the project subset is
never called PoseBusters.

## 6.1 Official PoseBusters condition

Official PoseBusters 0.6.5 is run with config `redock` against the same
conditioning molecule used for docking: waters deleted, native ligand removed,
and the manifest's retained site cofactors kept. The original waters are not
reintroduced, so a water test cannot be reported as a clash against a water
that docking never saw. Top-pose and all-pose official results are reported
separately.

## 7. Endpoint and statistics

Primary endpoint per case/seed:

- top-1 heavy-atom RMSD ≤ 2.0 Å;
- reference identity verified;
- no geometry error in any pose;
- status `passed`, `failed` or `skipped`.

Report:

- per-target, per-seed status and RMSD;
- per-target success across 5 seeds;
- overall success count over evaluable runs;
- mean/median RMSD and 95% bootstrap CI for the evaluable set;
- failures and skips separately;
- official PoseBusters pass rate, with version.

Skipped runs are never counted as passes. A target is not removed because it
performs poorly.

## 8. Evidence

Record:

- protocol hash;
- 12-target manifest and selection audit;
- environment and software versions;
- input SHA-256s;
- per-case/seed reports;
- PoseBusters version/results;
- failure/skip reasons;
- `SHA256SUMS`.

No raw PDB/SDF/PDBQT is committed. Restricted datasets are out of scope.

## 9. Stop conditions

Stop and do not report the primary benchmark if:

- a pilot ID appears in the primary manifest;
- a target is replaced after seeing its result;
- a per-case preparation override appears;
- raw restricted data is tracked;
- a skipped run is counted as a pass;
- official PoseBusters is replaced by the project subset without saying so.

A needed change creates a new protocol version; old records stay untouched.
