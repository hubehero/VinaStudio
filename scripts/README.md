# Scripts Index

Run scripts from the repository root with `uv run python scripts/<name>.py`.
They are development and release tools; the application itself does not import
this directory.

## Setup and build

| Script | Purpose |
|---|---|
| `fetch_samples.py` | Fetch the pinned 1IEP gold-standard inputs |
| `fetch_vina_cli.py` | Fetch the official Vina command-line binary |
| `build_1iep_reference.py` | Rebuild the 1IEP crystal-ligand reference |
| `build_web.py` | Build the Vue SPA into `vinastudio/server/static/` |
| `dev.py` | Hot-reload development: API + Vite + Qt |

## Validation and benchmark

| Script | Purpose |
|---|---|
| `validate_benchmark.py` | Run the redocking manifest; supports `--seeds` |
| `fetch_benchmark_data.py` | Fetch/verify pinned **open** benchmark resources |
| `audit_open_targets.py` | Audit PoseBusters candidates and freeze a selection |
| `build_benchmark_reference.py` | Extract a PDB ligand reference onto a CCD graph |
| `build_benchmark_manifest.py` | Build the confirmatory manifest from an audit |
| `summarize_benchmark.py` | Aggregate multi-seed reports |
| `run_posebusters.py` | Official PoseBusters adapter/status record |
| `check_benchmark_policy.py` | Offline licence/redistribution/path gate |

## Legacy/local tools

| Script | Status |
|---|---|
| `validate_experiment.py` | Historical experiment comparison; not current evidence |
| `validate_multi_system.py` | Historical multi-system probe; not current evidence |
| `probe_*.py` | Local session probes; not part of the release workflow |

## Rules

- Never commit `.benchmark-data/`, `validation-output/`, or raw third-party
  structures.
- Do not automate registration or licence acceptance for PDBbind/DUD-E/ZINC.
- New user-facing documentation belongs in `docs/`; validation evidence belongs
  in `validation/`; script notes belong here.
