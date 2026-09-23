# VinaStudio

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![AutoDock Vina 1.2.7](https://img.shields.io/badge/AutoDock-Vina-1.2.7-green.svg)](https://vina.scripps.edu/)

VinaStudio is a graphical desktop application built around [AutoDock Vina 1.2.7](https://vina.scripps.edu/), designed to help researchers and students get started with molecular docking without memorizing command-line flags or hand-editing configuration files.

Instead of stitching together separate tools for receptor preparation, ligand parameterization, box setup, docking runs, and result inspection, VinaStudio brings the entire workflow into a single window: load your PDB or SDF files, visually define the binding site, launch the docking with a click, and browse ranked poses with energy breakdowns and interaction maps — all in one place.

The application is built with PySide6 (Qt) on the desktop side and a Vue 3 single-page application for the interface, communicating over a local REST API. It runs on Linux, macOS, and Windows.

> **Note:** VinaStudio is intended for learning and exploratory research. It has not been extensively validated against benchmark datasets and should not be cited as a primary tool in publications. For production docking campaigns, please use AutoDock Vina directly or validated workflows.

[中文文档](README.zh-CN.md) | [用户指南](docs/USER_GUIDE.md) | [架构文档](docs/ARCHITECTURE.md)

---

## Features

- **Receptor & Ligand Preparation** — PDB/CIF/mmCIF → PDBQT for receptors, MOL/SDF/MOL2/PDB → PDBQT for ligands via Meeko, with options to remove waters, strip heteroatoms, and normalise atom ordering
- **Binding-Site Definition** — automatic box around ligand or receptor heavy atoms, with manual center/size input and 3D visualisation
- **Molecular Docking** — Vina, Vinardo, and AutoDock4 scoring functions with full parameter control (exhaustiveness, seeds, energy range, etc.)
- **Batch Docking** — process multiple ligands sequentially with progress tracking and CSV export
- **Result Analysis** — pose ranking by affinity, RMSD clustering, energy decomposition, and hydrogen-bond / hydrophobic / ionic interaction detection
- **3D Visualisation** — interactive molecular viewer powered by 3Dmol.js, with cartoon, stick, sphere, and surface representations
- **RCSB PDB Integration** — search and download receptors and ligands directly from the PDB database
- **Project Management** — save and restore complete docking sessions as `.vinaproj` files
- **Bilingual UI** — Chinese and English interface, switchable at any time
- **API Documentation** — built-in Swagger UI accessible from the settings dialog

## Requirements

- Linux, macOS, or Windows
- Python 3.12
- [uv](https://docs.astral.sh/uv/) (package manager)
- Node.js 20+ and [pnpm](https://pnpm.io/) (for building the frontend)

## Quick Start

```bash
# Clone the repository
git clone https://github.com/hubehero/VinaStudio.git
cd VinaStudio

# Install dependencies
uv sync --extra dev

# Build the frontend
pnpm -C web install
pnpm -C web build

# Launch the application
uv run python -m vinastudio
```

## Development

Run with hot reload:

```bash
uv run python scripts/dev.py
```

Run tests and linters:

```bash
uv run pytest -q
uv run ruff check .
pnpm -C web typecheck
```

## Architecture

| Layer | Location | Description |
|-------|----------|-------------|
| Desktop Shell | `vinastudio/desktop/` | PySide6 window, native menus, QWebChannel bridge |
| API Server | `vinastudio/server/` | FastAPI on loopback, WebSocket job streaming |
| Domain Core | `vinastudio/core/` | Docking, preparation, and analysis logic |
| Frontend | `web/` | Vue 3 + 3Dmol.js SPA |

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for detailed design decisions.

## Supported Formats

| Type | Input Formats |
|------|---------------|
| Ligands | `.sdf`, `.mol`, `.mol2`, `.pdb`, `.pdbqt` |
| Receptors | `.pdb`, `.cif`, `.mmcif`, `.ent`, `.pdbqt` |

## Acknowledgments

This project is built upon the following open-source software:

- **[AutoDock Vina 1.2.7](https://vina.scripps.edu/)** — The molecular docking engine developed by The Scripps Research Institute. Licensed under [Apache License 2.0](https://github.com/ccsb-scripps/AutoDock-Vina/blob/develop/LICENSE).
- **[Meeko](https://github.com/forlilab/Meeko)** — Molecular preparation tool for AutoDock Vina. Licensed under [Apache License 2.0](https://github.com/forlilab/Meeko/blob/master/LICENSE).
- **[RDKit](https://www.rdkit.org/)** — Cheminformatics toolkit. Licensed under [BSD 3-Clause](https://github.com/rdkit/rdkit/blob/master/license.txt).
- **[3Dmol.js](https://3dmol.org/)** — Molecular visualization library. Licensed under [MIT License](https://github.com/3dmol/3Dmol.js/blob/master/LICENSE).
- **[Vue.js](https://vuejs.org/)** — Progressive JavaScript framework. Licensed under [MIT License](https://github.com/vuejs/vue/blob/dev/LICENSE).
- **[PySide6](https://doc.qt.io/qtforpython-6/)** — Qt for Python. Licensed under [LGPL](https://doc.qt.io/qtforpython-6/license.html).
- **[FastAPI](https://fastapi.tiangolo.com/)** — Modern Python web framework. Licensed under [MIT License](https://github.com/fastapi/fastapi/blob/master/LICENSE).

### AI-Assisted Development

This project was developed with the assistance of [Claude](https://claude.ai/), an AI assistant by Anthropic. Claude was used for:

- Code generation and refactoring
- Bug identification and debugging
- Documentation writing
- Architecture design discussions
- Test case development

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

This project is licensed under the MIT License — see [LICENSE](LICENSE) for details.

**Note:** This project uses AutoDock Vina 1.2.7, which is licensed under the Apache License 2.0. The Apache License 2.0 is compatible with the MIT License. Users must comply with the terms of both licenses when using or distributing this software.

## Citation

If you use VinaStudio in your research, please cite:

```bibtex
@software{vinastudio2026,
  title = {VinaStudio: A Modern Desktop Workbench for AutoDock Vina},
  year = {2026},
  url = {https://github.com/hubehero/VinaStudio}
}
```

And cite the underlying tools:

```bibtex
@article{trott2010,
  title = {AutoDock Vina: Improving the speed and accuracy of docking with a new scoring function, efficient optimization, and multithreading},
  author = {Trott, Oleg and Olson, Arthur J.},
  journal = {Journal of Computational Chemistry},
  volume = {31},
  number = {2},
  pages = {455--461},
  year = {2010}
}
```

---

**Disclaimer:** This software is intended for scientific research and educational purposes only. Users assume all responsibility for molecular docking research conducted with this tool.
