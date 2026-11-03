# VinaStudio

**English** · [简体中文](README.md)

[![Release](https://img.shields.io/github/v/release/hubehero/VinaStudio?label=release)](https://github.com/hubehero/VinaStudio/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Platforms](https://img.shields.io/badge/platforms-Linux%20%7C%20Windows-lightgrey.svg)](#install)
[![AutoDock Vina](https://img.shields.io/badge/AutoDock%20Vina-1.2.7-2f8f83)](https://github.com/ccsb-scripps/AutoDock-Vina)

VinaStudio is a desktop front end for AutoDock Vina. Vina still runs the
docking. VinaStudio handles receptor and ligand preparation, binding-site setup,
starting jobs, reviewing results, and keeping the parameters, inputs and logs
from each run with the job. It is for people who repeat the same workflow often
and would rather not rebuild the command line every time.

![VinaStudio interface overview](https://github.com/user-attachments/assets/52492a9f-e995-40f5-bf5b-4ff35f6c4bc9)

Top left is a docking result; top right is the workbench; bottom left is the
molecule catalog; bottom right is the results report.

## Features

- Receptor PDB/mmCIF to PDBQT; ligand MOL/SDF/MOL2/SMILES to 3D PDBQT through Meeko.
- A box derived from a ligand or residue selection, or entered by hand and
  adjusted in the 3D view.
- Docking with Vina, Vinardo or AutoDock4, with run stages, streamed logs and
  cancellation.
- Pose review, per-pose energy breakdown, redocking RMSD, geometry checks and
  2D/3D interaction maps.
- A catalog for receptors, ligands, Studies, collections and screening
  libraries, with 125 common drug entries included.
- CSV, pose, HTML report and project export; searchable history with
  favourites, tags and comparison.

## Install

### Windows

Download `vinastudio-<version>-setup.exe` and `SHA256SUMS` from
[Releases](https://github.com/hubehero/VinaStudio/releases), check the SHA-256,
then run it. The installer is per-machine, needs administrator rights and is
unsigned, so SmartScreen will ask for confirmation. Python, the scientific
dependencies and the Vina 1.2.7 command-line engine are bundled.

The limits are documented in [Windows support](docs/WINDOWS.md): AutoDock4 needs
external maps, antialiasing is off by default, only x64 is supported, and there
is no auto-update.

### Linux

Download the `.deb` or portable tarball from Releases. Install the package with
`sudo apt install ./vinastudio_<version>_amd64.deb`, or unpack the tarball and
run `vinastudio/vinastudio`.

### From source

You need Python 3.12, [uv](https://docs.astral.sh/uv/), Node.js 22+ and
[pnpm](https://pnpm.io/).

```bash
pnpm -C web install
pnpm -C web build            # build the SPA into vinastudio/server/static first
uv sync --extra dev
uv run python -m vinastudio
```

## Try the 1IEP example

1. Open the application and click **Set up the 1iep example** on the Workbench.
2. Check the receptor, ligand and automatic box, then open **Docking**.
3. Keep the default Vina, exhaustiveness 8 and 20 poses; click **Start docking**.
4. Use the results page for poses and interactions, and **Results report** for
   the parameters and charts from this run.

This is a software control, not a general accuracy claim. More detail is in the
[user guide](docs/USER_GUIDE.md).

## Validation

The repository keeps the actual run records:

- 1IEP redocking: top-pose RMSD 0.353 Å, best affinity −13.286 kcal/mol,
  5 poses, 0 geometry errors.
- 12 pre-registered open targets × 5 seeds: 60/60 passed, mean top-1 RMSD
  0.5343 Å, bootstrap 95% CI [0.4710, 0.6020] Å.
- Official PoseBusters 0.6.5 (`redock`, same prepared structures as docking):
  60/60 top poses passed, 7/60 of all poses passed.

These numbers apply only to that open set and protocol. They are not PDBbind/CASF
results, a general accuracy claim, an enrichment claim or an experimental binding
free energy. Protocols, failures and raw reports are in
[Academic validation](docs/ACADEMIC_VALIDATION.md) and the
[benchmark record](validation/benchmark/records/2026-11-02-open-posebusters-v1/).

## Implementation

The code has four layers:

| Layer | Location | Responsibility |
|---|---|---|
| Desktop shell | `vinastudio/desktop/` | Qt window, native menus, QWebChannel bridge |
| API | `vinastudio/server/` | FastAPI on loopback, serves the UI, streams job events |
| Core | `vinastudio/core/` | Preparation, docking and analysis; no Qt or FastAPI dependency |
| Interface | `web/` | Vue 3 + 3Dmol.js |

The UI is served over local HTTP, not `file://`. Docking runs in spawned child
processes because Vina has no cancellation API. PDBQT is never rendered directly;
Meeko converts poses to SDF. The reasoning and details are in
[Architecture](docs/ARCHITECTURE.md).

## Documentation

- [User guide](docs/USER_GUIDE.md) · [简体中文](docs/USER_GUIDE.zh-CN.md)
- [Documentation index](docs/README.md) · [Windows support](docs/WINDOWS.md)
- [Academic validation and scope](docs/ACADEMIC_VALIDATION.md)
- [Validation method and reproduction](docs/VALIDATION.md)
- [Changelog](CHANGELOG.md) · [Contributing](CONTRIBUTING.md) ·
  [Security](SECURITY.md)

## Development

These commands need the development tree; the public release tree does not
include the tests or `scripts/dev.py`.

```bash
uv run python scripts/dev.py   # API + Vite + Qt with hot reload
./web_start.sh                 # web interface only
uv run pytest -q
uv run ruff check .
pnpm -C web typecheck
```

## License

The code is MIT-licensed; see [LICENSE](LICENSE) and
[THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).

Main dependencies and references: [AutoDock Vina](https://github.com/ccsb-scripps/AutoDock-Vina),
[Meeko](https://github.com/forlilab/Meeko), [RDKit](https://www.rdkit.org/),
[3Dmol.js](https://3dmol.csb.pitt.edu/), [Vue 3](https://vuejs.org/),
[Element Plus](https://element-plus.org/) and
[PySide6](https://doc.qt.io/qtforpython/).
