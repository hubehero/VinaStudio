# VinaStudio

A modern desktop workbench for **AutoDock Vina** docking: a Vue 3 + 3Dmol.js
interface running inside a **PySide6** embedded browser, backed by the official
`vina` Python API and **Meeko** for molecular parameterisation and format
conversion.

Chinese documentation: [README.zh-CN.md](README.zh-CN.md)
**User Guide (step-by-step for beginners)**: [docs/USER_GUIDE.md](docs/USER_GUIDE.md)

---

## What it is

AUTO Dock Vina is excellent but command-line only, and its Python API is a set
of blocking calls. VinaStudio wraps both in a desktop application that is
pleasant to use and stays scientifically honest:

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
- **Bilingual** — Chinese and English, Chinese by default.

## Requirements

- Linux, macOS or Windows
- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- Node.js 20+ and [pnpm](https://pnpm.io/) (only to build the interface)

## Install and run

```bash
uv sync --extra dev          # create .venv and install the scientific stack
pnpm -C web install          # interface dependencies
pnpm -C web build            # build the interface into vinastudio/server/static
uv run python -m vinastudio  # launch the desktop application
```

`scripts/build_web.py` wraps the two pnpm steps.

## Development

Run the interface with hot reload against a live API:

```bash
uv run python scripts/dev.py
```

This starts the API on a fixed loopback port, the Vite dev server, and the Qt
window pointed at Vite. Edit anything under `web/src` and the window updates
without a restart.

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
- **Structure input** — SMILES to 3D ligand, the built-in 2D sketcher (see
  above), and a molecule manager for batch inspection and preparation.
- **Rendering diagnostics** — GPU/software renderer visibility with quality
  tiers; native file dialogs on the desktop, upload fallback in a browser.

See the roadmap in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

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
