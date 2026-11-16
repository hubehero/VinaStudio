# Headless CLI

**English** · [简体中文](CLI.zh-CN.md) · [Home](../README.en.md)

`vinastudio-cli` runs preparation, docking, validation and export without Qt or
an HTTP server. It imports `vinastudio.core`, not the desktop shell or FastAPI,
and shares `run_docking`/`prepare_*` with the application.

## Install

The base package is core + CLI + local API server. The desktop shell is the
optional `desktop` extra:

```bash
pip install vinastudio                 # CLI/API only
pip install "vinastudio[desktop]"      # plus the Qt application
```

From a source checkout:

```bash
uv sync --extra dev                    # developer environment (includes Qt)
uv run vinastudio-cli version --json
```

`vinastudio` with no subcommand still starts the desktop application; use
`vinastudio-cli` (or `vinastudio <subcommand>`) for headless work. Without the
`desktop` extra, no-argument `vinastudio` prints an install hint and exits 2.

## Commands

| Command | Purpose |
|---|---|
| `prepare receptor -i rec.pdb -o prep/` | Receptor PDBQT/PDB + report |
| `prepare ligand -i lig.sdf -o prep/` | Ligand PDBQT/SDF + report |
| `dock --config job.json --out out/result.json` | One docking run + `result.json` |
| `screen --config screen.json --out ranking.csv` | Sequential library screen + ranking |
| `validate --manifest manifest.json --out report/` | Redocking/cross-docking report |
| `export --result result.json --format complex-pdb,pml,cxc,plip-json --out exports/` | Pose artifacts and interop views |
| `server --host 127.0.0.1 --port 8000` | Local FastAPI server without Qt |
| `engines list/doctor --manifest engine.json` | Probe built-in and external engines |
| `version --json` | Software and engine versions |

One-shot commands accept `--json`; stdout then contains one JSON envelope and
nothing else. Engine progress is written to stderr. `server` is long-running and
does not use the envelope.

## Schema versions

The three headless contracts are versioned independently:

- **Inputs — `job.json` and `screen.json`:** the supported version is exactly
  `1.0`. Unknown fields are rejected so a typo is an input error (exit code 2),
  and a newer `1.x` input is rejected explicitly rather than silently ignored.
- **Output — `result.json`:** a `1.x` reader accepts a newer minor version and
  ignores unknown fields, so additive data does not break consumers. A `2.0`
  result requires a new reader; there is no automatic migration.
- Schemas are generated from the Pydantic models under `schemas/`
  (`job-1.0`, `result-1.0`, `screen-1.0`). A version change is a contract change,
  not a documentation-only edit.

## `job.json`

Paths are resolved relative to the job file (absolute paths are kept). The
strict schema is `schemas/job-1.0.schema.json`.

```json
{
  "schemaVersion": "1.0",
  "receptor": {"path": "receptor.pdb"},
  "ligand": {"path": "ligand.sdf"},
  "box": {
    "source": "manual",
    "center": [15.190, 53.903, 16.917],
    "size": [20.0, 20.0, 20.0]
  },
  "parameters": {"scoring": "vina", "exhaustiveness": 8, "nPoses": 9, "seed": 42},
  "reference": {"path": "reference.sdf", "rmsdThreshold": 2.0}
}
```

`box.source` is `manual` (needs centre and size) or `ligand` (autobox from the
ligand, optionally with `extend`). `.pdbqt` inputs are used as already prepared;
other inputs go through Meeko. Unknown fields are rejected.

## `result.json`

`schemas/result-1.0.schema.json` is the contract. `result.json` records:

- software, engine/backend/scoring versions;
- input paths and SHA-256 hashes;
- preparation reports and the search box source;
- docking parameters and relative artifact paths;
- per-pose affinity, Vina RMSD bounds, reference RMSD and the six project checks;
- provenance (command, host, cwd, environment, git state).

Readers ignore unknown fields, so a future minor version can add data. The
result is written atomically.

## `screen.json`

Screening is one sequential worker (`--parallelism 1` only); it reuses
the GUI's `screening_worker`, including lazy ligand preparation and per-entry
artifacts. The box must be manual because a library has no single ligand.

```json
{
  "schemaVersion": "1.0",
  "receptor": {"path": "receptor.pdbqt"},
  "libraryPath": "libraries/my-library",
  "box": {
    "source": "manual",
    "center": [15.190, 53.903, 16.917],
    "size": [20.0, 20.0, 20.0]
  },
  "parameters": {"exhaustiveness": 8, "nPoses": 9, "seed": 42},
  "labelsPath": "labels.csv"
}
```

`libraryPath` is a library directory (`index.json` + `mols/`). `entries` may
override the index with `{index, name, sdfPath?}` records. Outputs are
`ranking.csv`, `ranking.json`, per-entry artifacts under `ligands/`, and — when
`labelsPath` is supplied — `enrichment.json`/`enrichment.csv`. Label names must
match the library entry titles.

## Interop exports

```bash
vinastudio-cli export --result result.json \
  --format complex-pdb,pml,cxc,plip-json --out exports/
```

- `complex.pdb`: prepared receptor + the selected pose as `HETATM` residue
  `LIG`, chain `L`; ligand bonds are written as `CONECT`.
- `complex.pml` / `complex.cxc`: PyMOL and ChimeraX command files that load
  `complex.pdb`, show the cartoon and style the ligand.
- `interactions.plip.json`: a **PLIP-shaped mapping** of the project's six
  geometric contact rules. It is not a PLIP run: salt bridges remain candidates
  when formal charges are absent, halogen bonds are distance-only, and
  π-stacking is not reported. The document carries `mapping`, `byType` and a
  `disclaimer`.
- `--pose` selects the 1-based pose (default 1); `--cutoff` sets the contact
  search radius for `plip-json` (default 4.0 Å).

PML/CXC reference `complex.pdb`, so that file is written whenever either is
requested. No PyMOL/ChimeraX binary is required.

## External engines

An adapter is a JSON manifest plus a binary the user supplies; nothing is
downloaded or bundled. `engines list` includes the built-in Vina doors, and
`engines doctor` probes them plus any `--manifest` files.

```json
{
  "name": "example-engine",
  "version": "1.0",
  "license": "MIT (external)",
  "capabilities": ["dock"],
  "executable": "/opt/example/bin/dock",
  "command": ["{executable}", "--receptor", "{receptor}",
              "--ligand", "{ligand}", "--out", "{out}"],
  "output": "poses.pdbqt",
  "scoreNamespace": "example",
  "cancel": "process-kill",
  "timeout": 300
}
```

Supported placeholders: `{executable}`, `{receptor}`, `{ligand}`, `{out}`,
`{center_x/y/z}`, `{size_x/y/z}`, `{scoring}`, `{exhaustiveness}`, `{n_poses}`,
`{seed}`, `{flex}`. The command is executed without a shell; a missing binary
or capability raises `EngineCapabilityError`, non-zero exits are errors, and a
timeout kills the child. Results carry the manifest's `scoreNamespace`, so
scores from different engines are never mixed.

`ExternalEngine.dock()` is available through `vinastudio.api`; the `dock`
command still selects the built-in Vina doors, not an arbitrary external
manifest. GPL engines remain external and are never bundled.

## Server and Docker

`vinastudio-cli server` runs the local FastAPI app without Qt. It generates an
API token unless `VINASTUDIO_API_TOKEN`/`--token` is supplied; the token is
printed on stderr. Bind loopback by default; exposing it on `0.0.0.0` requires a
token and a deliberate port mapping.

The headless image is `docker/Dockerfile`:

```bash
docker build -f docker/Dockerfile -t vinastudio-headless .
docker run --rm vinastudio-headless version --json
docker run --rm -p 127.0.0.1:8000:8000 \
  -e VINASTUDIO_API_TOKEN=change-me \
  vinastudio-headless server --host 0.0.0.0 --port 8000
```

See [docker/README.md](../docker/README.md) for workspace mounts and limits.

## Exit codes

| Code | Meaning |
|---:|---|
| 0 | Success |
| 1 | Run failure, or a validation case failed |
| 2 | Invalid input/config/result |
| 3 | Engine unavailable |
| 4 | Cancelled |

`validate` also returns 1 when `--strict` is set and any case is skipped.

## 1IEP example

```bash
uv run vinastudio-cli prepare receptor \
  -i vinastudio/resources/sample/1iep/1iep_receptorH.pdb -o /tmp/1iep-prep --json
uv run vinastudio-cli prepare ligand \
  -i vinastudio/resources/sample/1iep/1iep_ligand.sdf -o /tmp/1iep-prep --json
uv run vinastudio-cli dock --config /tmp/1iep.job.json \
  --out /tmp/1iep-out --json
uv run vinastudio-cli validate --manifest validation/manifest.json \
  --case 1iep --out /tmp/1iep-val --json
```

The docked result is expected near −13.286 kcal/mol and 0.353 Å against the
1IEP reference; the validation command writes `validation-report.json` and
`.md`.

## Boundaries

- The CLI does not start HTTP and does not download data.
- Manifest paths resolve against the repository root, matching
  `scripts/validate_benchmark.py`; use absolute paths for external manifests.
- `validate` is a redocking/cross-docking harness, not a leaderboard.
- `screen` is one sequential worker, not HPC; it does not start HTTP.
- Enrichment metrics need a user-supplied label set; no dataset is bundled.
- External engines are not bundled; GPL engines remain external adapters.
- `analyze` is not part of the first CLI batches; complex PDB, PML, CXC and
  PLIP-shaped JSON export are available now.
