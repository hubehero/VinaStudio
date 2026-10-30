# VinaStudio

**English** · [简体中文](README.md)

[![Release](https://img.shields.io/github/v/release/hubehero/VinaStudio?label=release)](https://github.com/hubehero/VinaStudio/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Platforms](https://img.shields.io/badge/platforms-Linux%20%7C%20Windows-lightgrey.svg)](#requirements)

A modern desktop workbench for **AutoDock Vina** docking: a Vue 3 + 3Dmol.js
interface running inside a **PySide6** embedded browser, backed by the official
**AutoDock Vina 1.2.7** engine — the Python API where it exists, the packaged
command-line binary on Windows — and **Meeko** for molecular parameterisation
and format conversion.

**Documentation:** [User guide](docs/USER_GUIDE.md) · [Windows](docs/WINDOWS.md) · [Architecture](docs/ARCHITECTURE.md) · [Changelog](CHANGELOG.md)
**简体中文:** [README.md](README.md) · [用户手册](docs/USER_GUIDE.zh-CN.md) · [Windows 支持](docs/WINDOWS.zh-CN.md)

## Documentation

| Document | English | 简体中文 |
|---|---|---|
| User guide — install to export | [User guide](docs/USER_GUIDE.md) | [用户手册](docs/USER_GUIDE.zh-CN.md) |
| Windows support and limits | [Windows](docs/WINDOWS.md) | [Windows 支持](docs/WINDOWS.zh-CN.md) |
| Architecture and constraints | [Architecture](docs/ARCHITECTURE.md) | [架构](docs/ARCHITECTURE.zh-CN.md) |
| Academic validation and references | [Academic validation](docs/ACADEMIC_VALIDATION.md) | [学术验证](docs/ACADEMIC_VALIDATION.zh-CN.md) |
| Release notes | [CHANGELOG.md](CHANGELOG.md) | bilingual |
| Contributing | [CONTRIBUTING.md](CONTRIBUTING.md) | [贡献指南](CONTRIBUTING.zh-CN.md) |
| Code of conduct | [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) | [行为准则](CODE_OF_CONDUCT.zh-CN.md) |
| Security policy | [SECURITY.md](SECURITY.md) | [安全策略](SECURITY.zh-CN.md) |
| Release process | [RELEASING.md](RELEASING.md) | [发布流程](RELEASING.zh-CN.md) |
| License | [LICENSE](LICENSE) | MIT |

The API reference is served locally while the application runs, at **/docs**.

---

## What it is

AUTO Dock Vina is excellent but command-line only, and its Python API is a set
of blocking calls. VinaStudio wraps both in a desktop application that is
pleasant to use and stays scientifically honest. It is aimed at students and
labs who prepare receptors, define boxes, dock and review results repeatedly:
the command-line steps live in one window, and the parameters a run actually
used stay with its result.

What it does:

- **Receptor and ligand preparation** — PDB/CIF → PDBQT for receptors,
  MOL/SDF/MOL2 → PDBQT for ligands via Meeko. Inputs that are 2D or lack
  hydrogens are embedded and protonated before parameterisation.
- **Binding-site definition** — automatic bounding box from a ligand or a
  residue selection, or explicit centre and size, rendered and editable in 3D.
- **Docking** — Vina, Vinardo and AutoDock4 scoring functions with the full
  parameter surface exposed, live progress and streamed logs, and real
  cancellation.
- **Analysis** — pose ranking, per-pose energy decomposition, geometric
  interaction detection (hydrogen bonds, salt bridges, hydrophobic contacts)
  drawn as 3D annotations, plus a 2D interaction map.
- **Structure input** — SMILES to 3D ligand, and a built-in **2D sketcher**
  (template rings, chain tool, bond/stereo tools, one-click cleanup, periodic
  table and radicals) with a complete draw-to-export loop.
- **Online molecule library** — RCSB PDB structures/co-crystal ligands, plus
  PubChem/ChEMBL search by name/ID, similarity or substructure, with source,
  licence and 3D/needs-preparation labels.
- **Bilingual** — Chinese and English, Chinese by default.

## Requirements

| Platform | What is available |
|---|---|
| Linux (x86_64) | `.deb` and portable tarball, published |
| Windows 10 1809+ / 11 (x64) | Installer, verified on real hardware; published from **0.4.0** |
| macOS | Source only — not packaged or release-verified |

Running from source needs Python 3.12, [uv](https://docs.astral.sh/uv/), and
Node.js 22+ with [pnpm](https://pnpm.io/) (interface build and frontend tests). The Windows
installer bundles all of that, including the Vina engine.

## Install and run

### Windows

Download `vinastudio-<version>-setup.exe` from the
[releases page](https://github.com/hubehero/VinaStudio/releases), verify its
SHA-256, and run it. The installer is per-machine (administrator required) and
unsigned, so SmartScreen will ask for confirmation. It includes the AutoDock
Vina 1.2.7 command-line engine, which the application uses automatically because
the `vina` Python module has no Windows build.

The supported surface and the boundaries that matter — AutoDock4 maps,
antialiasing default, unsigned installer, x64 only — are documented in
[docs/WINDOWS.md](docs/WINDOWS.md).

### From source

```bash
uv sync --extra dev          # create .venv and install the scientific stack
pnpm -C web install          # interface dependencies
pnpm -C web build            # build the interface into vinastudio/server/static
uv run python -m vinastudio  # launch the desktop application
```

`scripts/build_web.py` wraps the two pnpm steps.

## Development

These commands need the development tree: the release mirror ships the application
and its packaging, but not the test suite or `scripts/dev.py`.

Run the interface with hot reload against a live API:

```bash
uv run python scripts/dev.py
```

This starts the API on a fixed loopback port, the Vite dev server, and the Qt
window pointed at Vite. Edit anything under `web/src` and the window updates
without a restart.

Start only the web interface (no Qt window) for browser testing:

```bash
./web_start.sh
```

The launcher stays in the foreground; Ctrl+C stops both the API and Vite, and a
file-manager double-click opens a terminal window automatically.

Run the checks:

```bash
uv run pytest -q
uv run ruff check .
pnpm -C web typecheck
```

## Architecture

Three layers with strict boundaries:

| Layer | Location | Responsibility |
|---|---|---|
| Desktop shell | `vinastudio/desktop/` | Qt window, native menus, QWebChannel bridge |
| API server | `vinastudio/server/` | FastAPI on loopback, serves the SPA, streams job events over WebSocket |
| Domain core | `vinastudio/core/` | Docking, preparation and analysis logic — no Qt, no FastAPI, fully unit-testable |
| Interface | `web/` | Vue 3 SPA rendered by the embedded Chromium |

Three constraints shape everything else, and are documented in
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md):

1. The interface is served over **local HTTP**, never `file://`, because ES
   modules are blocked by CORS on the file scheme.
2. Docking runs in **spawned child processes** — Vina has no cancellation API,
   so killing the process is the only way to stop a job, and `fork` is unsafe
   next to a live Qt event loop.
3. **PDBQT is never rendered directly.** 3Dmol.js does not parse it, and PDBQT
   carries no bond orders. Poses are converted to SDF by Meeko, which restores
   bond orders and formal charges from the SMILES recorded in the PDBQT header.

## Status

The project is being built in phases. What works today:

- Desktop shell (PySide6 + embedded Chromium), bilingual UI with theme
  switching, and an environment self-check that imports `vina`, `meeko` and
  `rdkit` for real
- **Ligand preparation** — MOL/SDF/MOL2/PDB → PDBQT through Meeko, reporting the
  hydrogens added, the conformer generated and the rotatable bonds found. The
  upstream 1iep reference PDBQT is reproduced byte for byte.
- **Receptor preparation** — PDB/mmCIF → PDBQT with Meeko's template matching,
  waters and non-polymer groups stripped on request, flexible sidechains split
  out, and the residue regroup that the official 1iep file needs.
- **Box and docking** — automatic or manual bounding box rendered and editable
  in 3D; Vina, Vinardo and AutoDock4 scoring, spawned jobs with live progress,
  streamed logs and real cancellation; batch docking with a leaderboard.
- **Analysis** — per-pose geometry validation, redocking RMSD reference,
  RMSD clustering, the 2D interaction map, and per-pose energy decomposition.
- **Persistence and export** — job history plus project save/reload across
  restarts, self-contained HTML result bundles, and a standalone results
  report page.
- **Molecule Catalog** — a workspace-level database that deduplicates
  receptors/ligands, groups receptor–ligand pairs into Studies and organises
  them with collections; server-side search, suggestions, bulk tags, screening
  libraries and virtual screening. The first workspace opens with 125 editable
  undergraduate drugs and migrates legacy data with a backup.
- **Structure input** — SMILES to 3D ligand, the built-in 2D sketcher (see
  above), and one Catalog import path for files, samples and online compound
  libraries.
- **Rendering diagnostics** — GPU/software renderer visibility with quality
  tiers; native file dialogs on the desktop, upload fallback in a browser.
- **Windows desktop package** — installer built by CI and verified on real
  hardware (preparation, docking, analysis, persistence, non-ASCII paths).
  Docking uses the bundled Vina 1.2.7 CLI; antialiasing is off by default
  because of the QtWebEngine Windows compositor flicker. See
  [docs/WINDOWS.md](docs/WINDOWS.md).

See the roadmap in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Community

- **Questions and bugs:** open a
  [GitHub issue](https://github.com/hubehero/VinaStudio/issues). Include the
  version, the operating system, the renderer string from the Environment page,
  and the relevant log excerpt.
- **Contributions:** read [CONTRIBUTING.md](CONTRIBUTING.md) first.
- **Conduct:** [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
- **Security:** report privately as described in [SECURITY.md](SECURITY.md);
  please do not open a public issue with exploit details.

VinaStudio is maintained by one person with help from contributors. Issues and
pull requests are read, but a reply may take a few days.

## References and acknowledgements

VinaStudio stands on the open-source ecosystem. The components below are
either direct dependencies or documented behavioural/specification
references (the license named is the upstream project's own):

- [AutoDock Vina](https://github.com/ccsb-scripps/AutoDock-Vina)
  (Apache-2.0) — the docking engine.
- [Meeko](https://github.com/forlilab/Meeko) (LGPL-2.1) — ligand and
  receptor PDBQT parameterisation.
- [RDKit](https://www.rdkit.org/) (BSD-3-Clause) — cheminformatics, SMILES
  handling and 2D depiction.
- [3Dmol.js](https://3dmol.csb.pitt.edu/) (BSD-3-Clause) — the WebGL
  molecular viewer.
- [MoleditPy](https://pypi.org/project/moleditpy/) (**GPL-3.0**) — the
  sketching *interaction model* of the built-in 2D sketcher (pointer
  semantics, keyboard shortcuts, rendering conventions) was studied as a
  behavioural specification.  VinaStudio's sketcher is an independent
  Vue 3 + SVG reimplementation: **no MoleditPy source code is included,
  linked or distributed with this project**, and it is not a dependency.
- [Vue 3](https://vuejs.org/) (MIT),
  [Element Plus](https://element-plus.org/) (MIT) — UI framework and
  components.
- [PySide6](https://doc.qt.io/qtforpython/) (LGPL-3.0) — Qt for Python
  desktop shell.

## License

MIT (see [LICENSE](LICENSE))
