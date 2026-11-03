# Validation and Evidence Index

This directory separates the executable validation harness from retained
evidence. It is not a second docs tree: protocol and interpretation live in
[`docs/VALIDATION.md`](../docs/VALIDATION.md) and
[`docs/ACADEMIC_VALIDATION.md`](../docs/ACADEMIC_VALIDATION.md).

| Path | Purpose | Data |
|---|---|---|
| `manifest.json` | Committed 1IEP redocking control | Committed sample only |
| `manifest.optional-2hyy.json` | Optional local negative control | Local sample, skipped when absent |
| `functional/` | User-facing feature matrix and UI evidence | Screenshots/reports |
| `functional/ui_smoke.py` | Production route smoke helper | No raw structures |
| `benchmark/` | Open benchmark policy, manifests, records | Open data fetched to `.benchmark-data/` |
| `benchmark/records/` | Confirmatory and pilot reports | No raw structures |
| `ci/smoke.py` | Release-tree backend API smoke | No Qt, network or full docking |

## Quick commands

```bash
# Committed 1IEP control
uv run python scripts/validate_benchmark.py --case 1iep --out-dir validation-output/1iep

# Open benchmark: verify pinned data, then run the frozen confirmatory set
uv run python scripts/fetch_benchmark_data.py \
  --manifest validation/benchmark/manifests/open-posebusters-v1.json \
  --out .benchmark-data --verify-only
uv run python scripts/validate_benchmark.py \
  --manifest validation/benchmark/manifests/open-posebusters-v1.json \
  --seeds 42,43,44,45,46 \
  --out-dir validation-output/benchmark-confirmatory

# Offline data-policy gate
uv run python scripts/check_benchmark_policy.py
```

## Data rules

- `.benchmark-data/` and `validation-output/` are gitignored.
- No PDBbind/CASF/DUD-E/ZINC raw data enters the repository or release tree.
- Restricted data is verified locally only; reports redact its paths.
- A skipped case is not a pass.
- The 1IEP result is a software control; the 12-target open result is limited to
  its pre-registered set. Neither is a universal accuracy claim.

See [`docs/README.md`](../docs/README.md) for the full documentation map.
