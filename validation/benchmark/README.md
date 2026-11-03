# VinaStudio Benchmark Data Policy

This directory is for **reproducible scientific benchmarks**, not for shipping a
convenience mirror of third-party databases. The executable plan and its
stop conditions live in the development plan; this file records the rules that
apply to every benchmark manifest and evidence record.

## What this layer may contain

| Tier | Purpose | Raw data in this repository |
|---|---|---|
| `open` | Public reproduction and CI | Allowed only after a licence review; prefer pinned downloads |
| `local-restricted` | Local scientific checks | **Never** |
| `attribution` | Data that requires notice/share-alike | Separate directory and licence, never relicensed as MIT |
| `unconfirmed` | Licence not confirmed in writing | **Never** |

`validation/benchmark/data/` and `.benchmark-data/` are ignored. A benchmark
record may contain reports, commands, hashes and aggregate metrics; it must not
contain PDBbind/CASF/DUD-E/ZINC structures, affinity tables, PDBQT files or
poses.

## Claim boundary

A redocking result on a pre-registered target set is a statement about that
protocol and those inputs. It is not:

- a universal docking-accuracy claim;
- an experimental binding-free-energy claim;
- an enrichment claim merely because a decoy set exists;
- comparable across scoring functions.

The committed 1IEP case remains a **software control**. The first multi-target
claim is allowed only after the 12-target open benchmark in the plan has a
complete, frozen protocol and report.

## Quick start

Phase 1 is offline and does not require data:

```bash
uv run pytest tests/unit/test_benchmark_manifest.py \
  tests/unit/test_benchmark_licenses.py \
  tests/unit/test_benchmark_scripts.py -q
uv run python scripts/check_benchmark_policy.py
```

The open pilots are in
[`records/2026-11-02-open-pilot/`](records/2026-11-02-open-pilot/) (v1: 1/4)
and [`records/2026-11-02-open-pilot-v2/`](records/2026-11-02-open-pilot-v2/)
(v2, cofactor-aware: 3/4; `5sis` still fails). They are exploratory plumbing
checks. The frozen confirmatory 12 × 5 run is in
[`records/2026-11-02-open-posebusters-v1/`](records/2026-11-02-open-posebusters-v1/).

Open data is fetched explicitly, never by the default test suite:

```bash
uv run python scripts/fetch_benchmark_data.py \
  --manifest validation/benchmark/manifests/open-posebusters-v1.json \
  --out .benchmark-data/open
```

Restricted data is verified locally only. The project never automates a login,
accepts a licence on the user's behalf, or stores credentials.

## Manifest levels

- `formatVersion: "1.0"` is the legacy 1IEP control format.
- `formatVersion: "1.1"` adds source, licence, redistribution and target
  provenance. New benchmark manifests must use 1.1.

The licence registry is `licenses.json`; human-readable source notes are in
`DATA_SOURCES.md`. A manifest is rejected if its licence and
`redistributable` flag disagree.

## Evidence rules

- Missing inputs are `skipped`, never `passed`.
- A pass means the configured RMSD/geometry conditions were met for the tested
  pose, not that the method is generally accurate.
- Every report records software versions, seed, input SHA-256 and licence.
- Restricted inputs are path-redacted; aggregate metrics may be published, raw
  files may not.
- Protocol changes create a new protocol file and a new record; old results are
  never rewritten.
