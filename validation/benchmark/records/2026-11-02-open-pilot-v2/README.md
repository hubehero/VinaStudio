# Open PoseBusters Pilot v2 — 2026-11-02

**Status:** cofactor-aware pilot; not a multi-target accuracy claim.
**Software:** VinaStudio 0.6.6 development tree; commit `94ccd73`, dirty tree.
**Manifest:** `validation/benchmark/manifests/open-posebusters-pilot-v2.json`
**Protocol:** `validation/benchmark/PROTOCOL-v2.md`
**Predecessor:** `records/2026-11-02-open-pilot/` (v1, retained unchanged)

## Result

| Case | Status | Best affinity | Best RMSD | Poses | Reason |
|---|---|---:|---:|---:|---|
| `5sb2` | passed | −12.446 kcal/mol | 0.508 Å | 5 | — |
| `5sd5` | passed | −8.355 kcal/mol | 0.584 Å | 5 | altloc A + NAP retained |
| `5sis` | failed | −8.941 kcal/mol | 5.714 Å | 9 | RMSD exceeds 2.0 Å |
| `6m2b` | passed | −10.179 kcal/mol | 1.630 Å | 5 | FMN/ORO retained |

**3 passed / 1 failed.** `5sis/JSM` remains a failure and is not excluded
silently. The v1 record remains the historical baseline.

## What changed from v1

- v1 used the default receptor preparation, deleting all non-water HETATM.
- v2 keeps only the ligand-site groups listed in the manifest:
  `A:201` (NAP) for 5SD5, `A:801/A:802` (ZN/MG) for 5SIS, and
  `A:401/A:402` (FMN/ORO) for 6M2B.
- 5SD5 uses `defaultAltloc: A` and allows the one unresolved template residue
  to be excluded, with that exclusion recorded in the report.
- Box, seed, ligand, target, threshold and scoring are unchanged.

## Inputs and licences

PDB entries CC0 1.0; PoseBusters target list MIT; ligand graphs from RCSB CCD
`*_ideal.sdf`; references from PDB HETATM coordinates via
`scripts/build_benchmark_reference.py`. Raw files live in gitignored
`.benchmark-data/` and are not in this record.

## Reproduction

```bash
uv run python scripts/validate_benchmark.py \
  --manifest validation/benchmark/manifests/open-posebusters-pilot-v2.json \
  --out-dir validation-output/benchmark-pilot-v2
```

## Limits

- One seed (`42`), one run per case.
- Four targets are a plumbing pilot, not the final deterministic 12-target set.
- `5sis` remains a failure; its ligand is large/peptidic, and this pilot does
  not establish whether the failure is search, preparation or chemistry.
- Affinity is not an experimental binding free energy.
