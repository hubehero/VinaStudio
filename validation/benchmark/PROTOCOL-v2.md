# Open Benchmark Pilot Protocol v2 (cofactor-aware)

**Status:** pilot v2; replaces v1's receptor-hetero policy, not its results.
**Date:** 2026-11-02
**Manifest:** `validation/benchmark/manifests/open-posebusters-pilot-v2.json`
**Predecessor:** `PROTOCOL.md` and `records/2026-11-02-open-pilot/` (v1)

## Why v2 exists

v1 used the default receptor preparation, which deletes every non-water HETATM.
The pilot showed:

- `5sd5` failed at PDB alternate-location parsing;
- `5sis` and `6m2b` docked to poses more than 8 Å from the native ligand.

The PDB entries place the pilot ligands next to chemically relevant groups:

- `5sd5/HWI` is 3.34 Å from `NAP A 201` (NADP cofactor);
- `5sis/JSM` is 5.69 Å from `MG A 802` and 5.95 Å from `ZN A 801`;
- `6m2b/EZO` is 4.18 Å from `FMN A 401`, with `ORO A 402` also present.

Deleting those groups creates a receptor that is not the deposited binding site.
v2 keeps exactly the listed cofactors/metals, selects altloc `A` for `5sd5`, and
allows the one Meeko-rejected residue to be excluded. No box, seed, threshold,
ligand, or target was changed.

## v2 changes

| Case | Change |
|---|---|
| `5sb2` | none |
| `5sd5` | `defaultAltloc: A`; `allowBadResidues: true`; keep `A:201` |
| `5sis` | keep `A:801`, `A:802` |
| `6m2b` | keep `A:401`, `A:402` |

Everything else is the v1 protocol: 22 Å native-ligand box, Vina scoring,
exhaustiveness 8, 9 poses, seed 42, RMSD ≤ 2.0 Å.

## Result (2026-11-02)

| Case | Status | Affinity | RMSD | Poses |
|---|---|---:|---:|---:|
| `5sb2` | passed | −12.446 | 0.508 Å | 5 |
| `5sd5` | passed | −8.355 | 0.584 Å | 5 |
| `5sis` | failed | −8.941 | 5.714 Å | 9 |
| `6m2b` | passed | −10.179 | 1.630 Å | 5 |

`5sis` remains a failure; v1 is retained as the pre-fix baseline.

## Reproduction

```bash
uv run python scripts/validate_benchmark.py \
  --manifest validation/benchmark/manifests/open-posebusters-pilot-v2.json \
  --out-dir validation-output/benchmark-pilot-v2
```

v1 results are retained separately. If v2 still fails, the failure is reported;
it is not converted into a pass by further per-case tuning.
