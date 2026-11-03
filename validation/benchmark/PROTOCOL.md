# Open Benchmark Pilot Protocol (v0.1)

**Status:** pilot only; not the final 12-target pre-registration.  
**Date:** 2026-11-02  
**Dataset:** `open-posebusters-pilot-v1`  
**Licence:** PDB-derived structures CC0 1.0; target list from PoseBusters-Benchmark (MIT).

## Scope

This pilot tests the benchmark plumbing on four PoseBusters entries before the
final 12-target list is frozen. It is deliberately not a general accuracy
claim. The target list was taken from the first usable entries in the published
PoseBusters list, not selected by the final deterministic selector.

The four cases are:

| ID | PDB ligand | PDB residue |
|---|---|---|
| `5sb2` | 1K2 | A 1006 |
| `5sd5` | HWI | A 202 |
| `5sis` | JSM | A 803 |
| `6m2b` | EZO | A 403 |

## Inputs

- Receptor: RCSB PDB entry, CC0.
- Ligand graph/input: RCSB Chemical Component Dictionary `*_ideal.sdf`.
- Reference: PDB HETATM coordinates copied onto the CCD graph by
  `scripts/build_benchmark_reference.py`; reference and input paths are
  distinct.
- Box: reference heavy-atom centroid, fixed 22 Å cube, even voxels if Vina
  requires them. No predicted pocket and no result-dependent adjustment.
- Vina engine/scoring: `vina`; exhaustiveness 8; 9 poses; seed 42.
- Pass threshold: top-1 heavy-atom RMSD ≤ 2.0 Å, no geometry error in any pose,
  reference identity verified.

## Run

```bash
uv run python scripts/fetch_benchmark_data.py \
  --manifest validation/benchmark/manifests/open-posebusters-pilot-v1.json \
  --out .benchmark-data --verify-only

# Reference generation, once per case (PDB + CCD inputs already fetched).
uv run python scripts/build_benchmark_reference.py \
  --pdb .benchmark-data/open/pilot/5SB2/5SB2.pdb \
  --ligand .benchmark-data/open/pilot/5SB2/1K2.sdf \
  --residue 1K2 --chain A --seq 1006 \
  --out-dir .benchmark-data/open/pilot/5SB2

uv run python scripts/validate_benchmark.py \
  --manifest validation/benchmark/manifests/open-posebusters-pilot-v1.json \
  --out-dir validation-output/benchmark-pilot
```

The equivalent reference commands for the other cases are encoded by their
`referenceSource` fields (`5SD5/HWI/A/202`, `5SIS/JSM/A/803`,
`6M2B/EZO/A/403`).

## Results

See `records/2026-11-02-open-pilot/`. The pilot outcome is **1 passed, 3 failed**:

- `5sb2` passed: −12.446 kcal/mol, RMSD 0.508 Å, 5 poses.
- `5sd5` failed before docking: PDB alternate-location parsing requires a
  deterministic altloc policy. Recorded as a preparation failure, not hidden.
- `5sis` failed: RMSD 8.577 Å; 9 poses.
- `6m2b` failed: RMSD 9.568 Å; 9 poses.

## Consequence for the final benchmark

The pilot shows the data/verification/report path works, but it is not a claim
of multi-target accuracy. Before the 12-target run:

- freeze the deterministic selector output;
- exclude or define a policy for covalent/altloc/cofactor-heavy entries;
- add multiple seeds and official PoseBusters;
- record failures as failures; no target/seed/threshold changes after results.
