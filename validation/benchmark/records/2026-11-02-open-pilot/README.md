# Open PoseBusters Pilot — 2026-11-02

**Status:** pilot; not a multi-target accuracy claim.
**Software:** VinaStudio 0.6.6 development tree; commit `94ccd73`, dirty tree.
**Manifest:** `validation/benchmark/manifests/open-posebusters-pilot-v1.json`
**Protocol:** `validation/benchmark/PROTOCOL.md`

## Result

| Case | Status | Best affinity | Best RMSD | Poses | Reason |
|---|---|---:|---:|---:|---|
| `5sb2` | passed | −12.446 kcal/mol | 0.508 Å | 5 | — |
| `5sd5` | failed | — | — | 0 | PDB alternate-location read failure |
| `5sis` | failed | −9.067 kcal/mol | 8.577 Å | 9 | RMSD exceeds 2.0 Å |
| `6m2b` | failed | −10.017 kcal/mol | 9.568 Å | 9 | RMSD exceeds 2.0 Å |

`5sb2` is one pass. It is not evidence that the other three targets, or unseen
targets, will pass. The failures are retained.

## Inputs and licences

- PDB entries: CC0 1.0; source URLs and SHA-256 are in the manifest.
- PoseBusters target list: MIT; structural inputs are PDB-derived.
- Ligand graphs: RCSB Chemical Component Dictionary `*_ideal.sdf`.
- Reference coordinates: PDB HETATM, extracted by
  `scripts/build_benchmark_reference.py`.
- Raw structures were downloaded into `.benchmark-data/` and are **not**
  included in this record or any commit.

## Reproduction

```bash
uv run python scripts/fetch_benchmark_data.py \
  --manifest validation/benchmark/manifests/open-posebusters-pilot-v1.json \
  --out .benchmark-data --verify-only

uv run python scripts/validate_benchmark.py \
  --manifest validation/benchmark/manifests/open-posebusters-pilot-v1.json \
  --out-dir validation-output/benchmark-pilot
```

The reference-generation commands are in `validation/benchmark/PROTOCOL.md`.
The report is schema 2.1 and includes the dataset licence summary, per-case
licence/redistributable flags, input hashes and the 22 Å box provenance.

## Known limits

- One seed (`42`) and one run per case; no confidence interval.
- The four targets were not selected by the final deterministic 12-target
  selector; they are a plumbing pilot.
- `5sd5` exposes an altloc policy gap; it is not silently excluded.
- `5sis` may be a covalent/cofactor-associated ligand; this needs review before
  the final selection, not a post-hoc pass.
- Vina affinity is not an experimental binding free energy.
