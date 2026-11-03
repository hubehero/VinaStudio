# Confirmatory Open PoseBusters 12 × 5 — 2026-11-02

**Status:** primary confirmatory redocking result for the frozen open set.
**Scope:** 12 pre-registered open targets, 5 seeds each (60 case/seed runs).
**Not a claim of universal docking accuracy.** The pilot v1/v2 and 5SIS are
separate exploratory records.

## Protocol

- Protocol: `validation/benchmark/PROTOCOL-confirmatory.md`
  SHA-256 `076018de90566bdff0fb0da242f80118deae7894de89df9cf4fd19df93539889`
- Manifest: `validation/benchmark/manifests/open-posebusters-v1.json`
  SHA-256 `ef6c7df25d963eac7b25fb245c2e40c41613c6710bbe48af4159c58b90080597`
- Audit/selection: `validation/benchmark/manifests/open-posebusters-audit.json`
  SHA-256 `e584aa923c9671e60bb338649dcbc2b4e9b0532062c9235439395e6c9ccadf33`
- Selection seed: 20261102
- Excluded pilot IDs: 5SB2, 5SD5, 5SIS, 6M2B
- 12 targets: 8DHG, 7ZU2, 8AEM, 7NPL, 7WQQ, 8DSC, 7R59, 8BOM, 7LOE, 7QGP, 7XJN, 7AKL

## Preparation

- PDB native ligand reference; CCD `*_ideal.sdf` input graph.
- 22 Å native-ligand box.
- `defaultAltloc = A`; excluded template residues recorded.
- Non-water HETATM within 6.0 Å of native ligand retained; waters/buffers removed.
- Vina scoring, exhaustiveness 8, 9 poses.
- Docking seeds 42–46.

## Result

**60 passed / 0 failed / 0 skipped.**

- Mean top-1 RMSD: **0.5343 Å**
- Median top-1 RMSD: **0.4854 Å**
- Bootstrap 95% CI (mean): **[0.4710, 0.6020] Å**
- Every target passed all five seeds in this run.

This is a strong result **on this pre-registered open set**. It does not establish
accuracy on PDBbind/CASF, unseen chemical space, enrichment, or binding-affinity
prediction.

## Official PoseBusters

Official PoseBusters **0.6.5**, config `redock`, was run against the same
prepared condition used for docking: native ligand removed, waters deleted,
site cofactors retained. The project's six geometry checks are not relabelled
as official PoseBusters.

- **Top-pose official pass: 60/60**
- **All-pose official pass: 7/60**
- Errors: 0

```bash
uv run --with posebusters==0.6.5 python scripts/run_posebusters.py \
  --report validation-output/benchmark-confirmatory/validation-report.json \
  --out validation-output/benchmark-confirmatory/posebusters.json
```

The two numbers are intentionally separate: a top-ranked pose can pass while a
lower-ranked pose fails. `posebusters.json` contains the per-case/seed and
per-pose checks.

## Evidence and data

- `report.json` / `report.md`: 60 case/seed records, schema 2.1.
- `summary.json` / `summary.md`: per-target and seed aggregation.
- `posebusters.json`: official-tool status.
- `SHA256SUMS`: record integrity.

Raw PDB/SDF/PDBQT/reference files remain in gitignored `.benchmark-data/` and
are not part of this record. Inputs are pinned by SHA-256 in the manifest.

## Pilot appendix

`records/2026-11-02-open-pilot/` (v1: 1/4) and
`records/2026-11-02-open-pilot-v2/` (v2: 3/4; 5SIS remains a failure) are
exploratory and are not included in the 60-run primary denominator.
