# VinaStudio

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![AutoDock Vina](https://img.shields.io/badge/AutoDock-Vina-1.2.7-green.svg)](https://vina.scripps.edu/)

A modern desktop workbench for **AutoDock Vina** molecular docking, providing a graphical interface for receptor/ligand preparation, binding-site definition, docking execution, and result analysis.

**基于 AutoDock Vina 开发的现代分子对接桌面工作台。**

[中文文档](README.zh-CN.md) | [用户指南](docs/USER_GUIDE.md) | [架构文档](docs/ARCHITECTURE.md)

---

## Features

- **Receptor & Ligand Preparation** — PDB/CIF/mmCIF → PDBQT for receptors, MOL/SDF/MOL2/PDB → PDBQT for ligands via Meeko
- **Binding-Site Definition** — automatic or manual docking box with 3D visualization
- **Molecular Docking** — Vina, Vinardo, and AutoDock4 scoring functions with full parameter control
- **Batch Docking** — process multiple ligands with CSV export
- **Result Analysis** — pose ranking, energy decomposition, interaction detection (H-bonds, hydrophobic, ionic)
- **3D Visualization** — interactive molecular viewer with multiple representation styles
- **RCSB PDB Integration** — download receptors and ligands directly from the PDB database
- **Project Management** — save and restore docking projects
- **Bilingual UI** — Chinese and English support

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

## Roadmap

- [x] Receptor and ligand preparation
- [x] Docking box configuration
- [x] Vina/Vinardo docking with progress tracking
- [x] Batch docking with CSV export
- [x] 3D visualization and interaction analysis
- [x] RCSB PDB database integration
- [x] Project management
- [ ] SMILES input support
- [ ] 2D molecular editor
- [ ] 2D interaction diagrams
- [ ] ADMET prediction
- [ ] Flexible residue docking
- [ ] Docker deployment

## Acknowledgments

This project is built upon the following open-source software:

- **[AutoDock Vina](https://vina.scripps.edu/)** — The molecular docking engine developed by The Scripps Research Institute. Licensed under [Apache License 2.0](https://github.com/ccsb-scripps/AutoDock-Vina/blob/develop/LICENSE).
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

All code has been reviewed, tested, and validated by human developers.

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

This project is licensed under the MIT License — see [LICENSE](LICENSE) for details.

**Note:** This project uses AutoDock Vina, which is licensed under the Apache License 2.0. The Apache License 2.0 is compatible with the MIT License. Users must comply with the terms of both licenses when using or distributing this software.

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

**免责声明：** 本软件仅供科学研究和教育目的。用户需自行承担使用本软件进行分子对接研究的风险和责任。
