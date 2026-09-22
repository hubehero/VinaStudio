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
  interaction detection (hydrogen bonds, salt bridges, π-stacking, hydrophobic
  contacts) drawn as 3D annotations.
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

- Desktop shell with the Vue interface, native menus and the QWebChannel bridge
- Bilingual UI with theme switching
- Environment self-check that imports `vina`, `meeko` and `rdkit` for real
- **Ligand preparation** — MOL/SDF/MOL2/PDB → PDBQT through Meeko, reporting the
  hydrogens added, the conformer generated and the rotatable bonds found. The
  upstream 1iep reference PDBQT is reproduced byte for byte.
- **Receptor preparation** — PDB → PDBQT with Meeko's template matching, waters
  and non-polymer groups stripped on request, flexible sidechains split out, and
  the residue regroup that the official 1iep file needs.
- **Rendering** — the prepared receptor is drawn as a cartoon and the ligand as
  sticks in the same viewport, over WebGL inside QtWebEngine.
- Native file dialogs in the desktop shell, with an upload fallback in a browser.

Docking and analysis land in the following phases; see the roadmap in
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## License

MIT
