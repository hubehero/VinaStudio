<h1 align="center">VinaStudio</h1>

<p align="center"><strong>A desktop workbench for AutoDock Vina</strong></p>

<p align="center"><strong>English</strong> · <a href="README.md">简体中文</a></p>

<p align="center">Prepare molecules, define the search box, run docking, review results, and keep the parameters and logs from every job in one place.</p>

<p align="center">
  <a href="https://github.com/hubehero/VinaStudio/releases"><img src="https://img.shields.io/github/v/release/hubehero/VinaStudio?label=release" alt="Release"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License: MIT"></a>
  <a href="#install"><img src="https://img.shields.io/badge/platforms-Linux%20%7C%20Windows-lightgrey.svg" alt="Platforms"></a>
  <a href="https://www.python.org/downloads/release/python-3120/"><img src="https://img.shields.io/badge/python-3.12-3776AB" alt="Python 3.12"></a>
  <a href="https://github.com/ccsb-scripps/AutoDock-Vina"><img src="https://img.shields.io/badge/AutoDock%20Vina-1.2.7-2f8f83" alt="AutoDock Vina"></a>
  <a href="https://hubehero.github.io/VinaStudio/experience/"><img src="https://img.shields.io/badge/docs-GitHub%20Pages-2f8f83" alt="Documentation"></a>
</p>

<p align="center">
  <a href="https://hubehero.github.io/VinaStudio/experience/">Interactive guide</a> ·
  <a href="docs/USER_GUIDE.md">User guide</a> ·
  <a href="docs/ARCHITECTURE.md">Architecture</a> ·
  <a href="docs/ACADEMIC_VALIDATION.md">Validation</a> ·
  <a href="https://github.com/hubehero/VinaStudio/releases">Releases</a>
</p>

---

<details>
<summary><strong>Contents</strong> · 17 sections</summary>

| Start | Use | Dive deeper |
|---|---|---|
| [Overview](#overview) | [Install](#install) | [Validation](#validation) |
| [At a glance](#at-a-glance) | [Run the 1IEP example](#run-the-1iep-example) | [How it works](#how-it-works) |
| [Interface preview](#interface-preview) | [FAQ](#faq) | [Repository layout](#repository-layout) |
| [Features](#features) | [Documentation](#documentation) | [Development](#development) |
| [Contributing](#contributing) | [Citation](#citation) | [Security](#security) |
| [License](#license) | [Acknowledgements](#acknowledgements) | [Releases](https://github.com/hubehero/VinaStudio/releases) |

</details>

## Overview

VinaStudio is a desktop workbench for [AutoDock Vina](https://github.com/ccsb-scripps/AutoDock-Vina). Vina still runs the docking. VinaStudio makes the surrounding workflow explicit and repeatable:

- prepares receptors and ligands as PDBQT files Vina can read;
- derives a search box from a ligand, residues or a candidate pocket, or lets you enter it by hand;
- runs Vina, Vinardo or AutoDock4, shows stages and logs, and can really cancel a job;
- puts poses, energies, RMSD, geometry checks and interactions on the same result page;
- keeps the parameters, input hashes, engine version and seed with each job.

It is for people who repeat the same workflow, compare several ligands, or would rather not rebuild a command line for every run.

> [!NOTE]
> VinaStudio does not implement a new scoring function, and it does not present a docking score as an experimental binding free energy. Energies from different scoring functions are not directly comparable; the interface and reports keep that boundary visible.

## At a glance

| Item | Detail |
|---|---|
| **Engine** | AutoDock Vina 1.2.7; Vinardo; AutoDock4 (requires external AutoGrid4 maps) |
| **Inputs** | Receptors: PDB, mmCIF. Ligands: MOL, SDF, MOL2, PDB, SMILES, and the built-in 2D sketcher |
| **Search space** | Ligand/residue-derived box, candidate pockets, manual centre and size, adjusted in the 3D view |
| **Results** | Pose review, per-pose energy breakdown, redocking RMSD, geometry checks, 2D/3D interaction maps |
| **Organisation** | Catalog for molecules, files, Studies, collections and screening libraries; 125 common drug entries included |
| **Exports** | PDBQT/SDF, CSV, HTML report, `.vinaproj` project, job records |
| **Platforms** | Linux x86_64, Windows 10 1809+/11 x64; macOS source attempts are possible but no package is published |
| **Interface** | PySide6 desktop shell, Vue 3 SPA, 3Dmol.js, loopback FastAPI |

## Interface preview

<p align="center">
  <img src="https://hubehero.github.io/VinaStudio/images/docking.png" alt="Docking result: poses, energy breakdown and interactions" width="900">
</p>

<p align="center"><sub>Docking result: poses, energy breakdown and interactions</sub></p>

<p align="center">
  <img src="https://hubehero.github.io/VinaStudio/images/workbench.png" alt="Workbench: preparation, box and docking steps" width="900">
</p>

<p align="center"><sub>Workbench: preparation, box and docking steps</sub></p>

<p align="center">
  <img src="https://hubehero.github.io/VinaStudio/images/molecules.png" alt="Molecule catalog: molecules, Studies, collections and libraries" width="900">
</p>

<p align="center"><sub>Molecule catalog: molecules, Studies, collections and libraries</sub></p>

<p align="center">
  <img src="https://hubehero.github.io/VinaStudio/images/report.png" alt="Results report: parameters, charts and job history" width="900">
</p>

<p align="center"><sub>Results report: parameters, charts and job history</sub></p>

The interactive field guide covers preparation, the box, job lifecycle, Catalog and validation: [open the interactive field guide](https://hubehero.github.io/VinaStudio/experience/).


## Features

### Preparation

- Receptors enter Meeko's Polymer path from PDB/mmCIF; selected waters, metals and cofactors can be kept, and flexible side chains can be split when needed.
- Ligands are read from MOL/SDF/MOL2/PDB/SMILES; when no 3D coordinates exist, RDKit generates a conformer and adds hydrogens.
- The preparation report covers hydrogen addition, 3D conformer generation, rotatable bonds, removed/kept groups and ignored residues.
- PDBQT keeps heavy atoms and polar hydrogens only. A lower atom count is a format consequence, not data loss.

### Box and sites

- Derive the box from a ligand, residues or candidate binding sites.
- Enter the centre and size by hand, then inspect and adjust it in the 3D view.
- Reject a box that contains no receptor atoms before launching, instead of returning a page of apparently successful `0.0` poses.
- Run single-ligand docking, batch docking and site-based screening.

### Docking and results

- Vina, Vinardo and AutoDock4 paths.
- Run stages, stdout logs, WebSocket events and a cancellable spawned worker.
- Pose ranking, affinity, per-pose energy breakdown and redocking RMSD.
- Geometry checks, clustering, interaction fingerprints and 2D/3D interaction maps.
- Job history with parameters, input hashes, engine version, seed and logs.

### Organisation and export

- Catalog for molecule identity, files, Studies, collections and screening libraries.
- Project files retain prepared artifacts and the current pipeline, so a session can be resumed.
- Export CSV, poses, HTML reports and result bundles for papers or reports.

## Install

### Windows

Download `vinastudio-<version>-setup.exe` and `SHA256SUMS` from [Releases](https://github.com/hubehero/VinaStudio/releases), verify the SHA-256, then run the installer.
The release also provides `BUILD-MANIFEST.json` with the tag, commit, CI run and per-asset SHA-256. It is a provenance record, not a signature.

The installer is per-machine, needs administrator rights and is **unsigned**, so SmartScreen asks for confirmation. It bundles Python, the scientific dependencies and the Vina 1.2.7 command-line engine. Windows 10 1809+ / 11 x64 is supported.

See [Windows support](docs/WINDOWS.md) for the boundaries: AutoDock4 needs external maps, antialiasing is off by default, only x64 is supported, and there is no silent auto-update; updates can be checked and downloaded manually in the app.

### Linux

Download the `.deb` or portable `.tar.gz` from Releases:

```bash
# Debian / Ubuntu
sudo apt install ./vinastudio_<version>_amd64.deb

# Portable bundle
tar -xzf vinastudio_<version>_linux_amd64.tar.gz
./vinastudio/vinastudio
```

### From source

You need Python 3.12, [uv](https://docs.astral.sh/uv/), Node.js 22+ and [pnpm](https://pnpm.io/).

```bash
pnpm -C web install
pnpm -C web build            # writes vinastudio/server/static
uv sync --extra dev
uv run python -m vinastudio
```

For interface-only work, run `pnpm -C web dev` and connect the Vite server to the local API.

## Run the 1IEP example

[1IEP](https://www.rcsb.org/structure/1IEP) is the control used throughout the project: c-Abl kinase with imatinib. It exercises preparation, the box, docking, results and the report.

1. Open the application and click **Set up the 1iep example** on the Workbench.
2. Check the receptor, ligand and automatic box; adjust it in the 3D view if needed.
3. Open **Docking**, keep the default Vina, `exhaustiveness=8` and 20 poses.
4. Start the job and follow the stages and log; use Cancel if you need to stop it.
5. Review poses, the energy breakdown and interactions; check the parameters and charts in the results report.

This is a software control, not a general accuracy claim. The full walkthrough is in the [user guide](docs/USER_GUIDE.md).

## Validation

The repository keeps the actual run records rather than a screenshot of a successful run:

| Record | Result |
|---|---|
| 1IEP redocking | top-pose RMSD **0.353 Å**; best affinity **−13.286 kcal/mol**; 5 poses; 0 geometry errors |
| 12 pre-registered open targets × 5 seeds | **60/60** passed; mean top-1 RMSD **0.5343 Å**; bootstrap 95% CI **[0.4710, 0.6020] Å** |
| Official PoseBusters 0.6.5 (`redock`) | **60/60** top poses; **7/60** of all poses |

> [!IMPORTANT]
> These numbers apply only to the pre-registered open set, protocol and preparation path. They are not PDBbind/CASF results, and they do not establish general accuracy, enrichment or an experimental binding free energy.

Protocols, failures, raw reports and references:

- [Academic validation and scope](docs/ACADEMIC_VALIDATION.md)
- [Validation method and reproduction](docs/VALIDATION.md)
- [Open benchmark record](validation/benchmark/records/2026-11-02-open-posebusters-v1/)
- [Benchmark protocol](validation/benchmark/PROTOCOL.md)

## How it works

VinaStudio has four layers with deliberate boundaries:

| Layer | Location | Responsibility |
|---|---|---|
| Desktop shell | `vinastudio/desktop/` | Qt window, native menus, QWebChannel file bridge |
| API | `vinastudio/server/` | Loopback FastAPI, static SPA, REST, WebSocket and JobManager |
| Domain core | `vinastudio/core/` | Preparation, box, docking, analysis, Catalog; no Qt or FastAPI imports |
| Interface | `web/` | Vue 3 + 3Dmol.js; talks to Python over HTTP + WebSocket only |

Three constraints shape the implementation:

1. **The UI is served over local HTTP, never `file://`.** ES modules have no usable origin on the file scheme; Qt starts Uvicorn on `127.0.0.1:0` and points the WebView at the assigned port.
2. **Docking runs in a spawned child process.** Vina has no cancellation API, so terminating the process is the only reliable stop; the parent owns the Qt and asyncio loops and cannot safely `fork`.
3. **PDBQT is never rendered directly.** 3Dmol cannot parse PDBQT and it has no bond orders; Meeko converts poses to SDF first.

The full runtime, process boundaries and docking lifecycle are in [Architecture](docs/ARCHITECTURE.md) and the [structure map](https://hubehero.github.io/VinaStudio/structure.html).

## Repository layout

<details>
<summary><strong>Expand the directory tree</strong></summary>

```text
vinastudio/
├── desktop/          Qt window, native menus, WebChannel, Uvicorn thread
├── server/           FastAPI, routers, JobManager, WebSocket
├── core/             preparation, box, docking, analysis, Catalog
│   ├── chem/         PDBQT, RDKit/Meeko, interactions, export
│   ├── catalog/      SQLite Catalog, search, migration
│   ├── engines/      Vina CLI adapter
│   └── worker.py     spawned child entry point
├── schemas/          request / response models
└── resources/        1IEP sample and validation resources

web/                  Vue 3 SPA
├── src/views/        workbench, molecules, box, docking, results
├── src/stores/       Pinia state
├── src/components/   panels, 3D viewport, dialogs, sketcher
└── src/api/          HTTP, WebSocket, QWebChannel

docs/                 user, architecture, Catalog, Windows docs and structure map
docs/experience/      interactive Pages field guide
validation/           1IEP control, functional matrix, open benchmark and PoseBusters records
scripts/              build, sample, validation and diagnostic tools
tests/                unit and integration tests
```

</details>

## Documentation

| Topic | Document |
|---|---|
| Install, prepare, dock, analyse and export | [User guide](docs/USER_GUIDE.md) · [简体中文](docs/USER_GUIDE.zh-CN.md) |
| Runtime, processes and docking lifecycle | [Structure map](https://hubehero.github.io/VinaStudio/structure.html) · [Text version](docs/STRUCTURE.md) |
| Four layers and three constraints | [Architecture](docs/ARCHITECTURE.md) · [简体中文](docs/ARCHITECTURE.zh-CN.md) |
| Molecules, files, Studies, collections and libraries | [Catalog](docs/MOLECULE_CATALOG.md) |
| Methods, results, failures and references | [Academic validation](docs/ACADEMIC_VALIDATION.md) · [简体中文](docs/ACADEMIC_VALIDATION.zh-CN.md) |
| Windows installation, limits and diagnostics | [Windows support](docs/WINDOWS.md) · [简体中文](docs/WINDOWS.zh-CN.md) |
| Interactive guide to principles and features | [Interactive Field Guide](https://hubehero.github.io/VinaStudio/experience/) |

The full index is [`docs/README.md`](docs/README.md).

## FAQ

### Why does the atom count drop after preparation?

PDBQT keeps heavy atoms and polar hydrogens; non-polar hydrogens are removed. The preparation report lists added hydrogens, the 3D conformer and the groups that were kept or removed. The lower count is a format conversion, not a damaged file.

### Why can't AutoDock4 start immediately?

AutoDock4 needs affinity maps generated in advance by AutoGrid4. The project does not bundle AutoGrid4 and will not invent maps in the background; use Vina or Vinardo without external maps. See [Windows support](docs/WINDOWS.md) and [Architecture](docs/ARCHITECTURE.md).

### Can I treat the docking score as a binding free energy?

No. Vina, Vinardo and AutoDock4 are simplified scoring functions. A score supports relative ranking within the same protocol; it is not an experimentally measured ΔG.

### What should I do about a flickering 3D view on Windows?

QtWebEngine 6's WebGL compositor can flicker on some Windows GPUs, so 3Dmol antialiasing is off by default. Adjust it in **Settings → Rendering quality**. This is a rendering issue, not a docking calculation.

### Where are jobs and project files stored?

The first launch asks for a workspace. Jobs go to `<workspace>/jobs/`; projects go to `<workspace>/projects/`. Completed jobs retain parameters, input hashes, engine version, seed and logs.

## Development

Run the application from source:

```bash
pnpm -C web install
pnpm -C web build
uv sync --extra dev
uv run python -m vinastudio
```

Development and checks:

```bash
uv run python scripts/dev.py   # API + Vite + Qt with hot reload
./web_start.sh                 # web interface only
uv run pytest -q
uv run ruff check .
pnpm -C web typecheck
pnpm -C web build:checked
```

Keep scientific logic in `vinastudio/core/`; it must not import Qt or FastAPI. User-facing copy changes must update both `web/src/i18n/locales/zh-CN.ts` and `en-US.ts`.

The public release tree (`vina_simple/`) intentionally does not ship the Python test suite; the `pytest` command above applies to the development tree. That tree contains 900+ unit and integration tests; the 1IEP control and validation records are linked under [Validation](#validation) and [Academic validation](docs/ACADEMIC_VALIDATION.md).

## Contributing

Reproducible bug reports, focused fixes and documentation improvements are welcome. Before opening a PR:

- search existing issues first;
- include the OS, version, reproduction steps and relevant logs;
- keep one problem per PR;
- update `CHANGELOG.md` when behaviour changes;
- run the checks you can run locally.

See [Contributing](CONTRIBUTING.md) · [简体中文](CONTRIBUTING.zh-CN.md) and the [Code of Conduct](CODE_OF_CONDUCT.md).

## Citation

If VinaStudio helps your research, cite the software and the methods it implements. The repository includes [`CITATION.cff`](CITATION.cff), and GitHub's **Cite this repository** button can generate a citation.

The main method references are the original AutoDock Vina paper, Meeko and RDKit; the full reference list and claim-evidence matrix are in [Academic validation](docs/ACADEMIC_VALIDATION.md).

## Security

VinaStudio runs entirely on the local machine: a Qt window, a loopback FastAPI service and spawned docking processes. State-changing API requests are origin-checked, the WebSocket handshake is validated separately, and the upload endpoint requires a custom request header.

Report security issues privately through GitHub Security rather than a public issue; see the [Security Policy](SECURITY.md).

## License

The code is released under the [MIT License](LICENSE). Third-party notices are in [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).

## Acknowledgements

VinaStudio builds on:

- [AutoDock Vina](https://github.com/ccsb-scripps/AutoDock-Vina): docking engine
- [Meeko](https://github.com/forlilab/Meeko): PDBQT parameterisation and pose conversion
- [RDKit](https://www.rdkit.org/): molecule I/O, conformers and cheminformatics
- [3Dmol.js](https://3dmol.csb.pitt.edu/): molecular visualisation
- [Vue 3](https://vuejs.org/) and [Element Plus](https://element-plus.org/): interface
- [PySide6](https://doc.qt.io/qtforpython/): desktop shell
