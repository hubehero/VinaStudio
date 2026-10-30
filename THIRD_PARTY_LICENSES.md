# Third-party notices

VinaStudio itself is MIT-licensed (see `LICENSE`).  Its distributed builds
include third-party components under their own licences.  This file is a
notice and index; the complete licence texts that are redistributable are in
`licenses/`.

| Component | Licence | Source / compliance |
|---|---|---|
| AutoDock Vina 1.2.7 | Apache-2.0 | https://github.com/ccsb-scripps/AutoDock-Vina ; text: `licenses/Apache-2.0.txt` |
| Meeko | LGPL-2.1 | https://github.com/forlilab/Meeko ; text: `licenses/LGPL-2.1.txt` |
| PySide6 / Qt for Python | LGPL-3.0 (or commercial Qt) | https://doc.qt.io/qtforpython/ ; text: `licenses/LGPL-3.0.txt` |
| RDKit | BSD-3-Clause | https://www.rdkit.org/ ; text: `licenses/RDKit-BSD.txt` |
| 3Dmol.js | BSD-3-Clause | https://3dmol.csb.pitt.edu/ |
| NumPy | BSD-3-Clause | https://numpy.org/ |
| SciPy | BSD-3-Clause | https://scipy.org/ |
| gemmi | MPL-2.0 | https://github.com/project-gemmi/gemmi |
| FastAPI / Starlette / Uvicorn | MIT / BSD / BSD | https://fastapi.tiangolo.com/ |
| Pydantic | MIT | https://docs.pydantic.dev/ |
| Vue 3 / Element Plus | MIT | https://vuejs.org/ / https://element-plus.org/ |

## LGPL relinking / replacement

PySide6 and Meeko are distributed as separate components inside the frozen
application.  The corresponding source is available from the upstream URLs
above.  A user who needs to replace or relink those libraries can use the
source distributions and the packaging specification in `packaging/`; the
application does not add a cryptographic lock that prevents replacement.
For a packaged build, the component files are under the PyInstaller
`_internal/` tree and the Qt/Meeko source versions are recorded by the release
build's lockfile and CI log.

## What is not covered

This notice does not relicense third-party code.  If a component's upstream
licence differs from the table, the upstream licence controls.  Paywalled
scientific articles cited in the academic report are **not** redistributed;
only their bibliographic metadata and DOI links are included.
