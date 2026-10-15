# Vina command-line binary

This directory holds the official AutoDock Vina binary that the CLI backend
(`vinastudio/core/engines/vina_cli.py`) runs. **The binaries are not committed** —
they are fetched, pinned by SHA-256, and bundled at build time:

```bash
uv run python scripts/fetch_vina_cli.py               # for this platform
uv run python scripts/fetch_vina_cli.py --all         # every listed platform
```

| File | Platform | Pinned |
|---|---|---|
| `vina` | Linux x86_64 | 4 056 088 bytes, `f31f774f…0644` |
| `vina.exe` | Windows x86_64 | 1 233 920 bytes, `e0c4b271…cce5` |

## Why a binary at all

The Python module `from vina import Vina` (what the default backend uses) has no
Windows wheel, and conda-forge publishes no `win-64` build either — so on Windows
the command-line binary is the only way to reach the same engine. With a fixed
seed the two agree exactly (verified on 1iep), which is why the CLI backend is
held to the same golden expectations. Background and the alternatives that were
rejected: `exchange/design/TASK-21-windows-feasibility-spike.md`.

## Licence

AutoDock Vina is **Apache-2.0** (<https://github.com/ccsb-scripps/AutoDock-Vina>).
Redistributing it in a packaged build is allowed and requires keeping its licence
and notice — packaging must ship Vina's `LICENSE` alongside the binary. The
Windows binary also needs the Microsoft Visual C++ runtime, which
`packaging/windows/vinastudio.iss` already handles (`VcRedistUrl`).

No source from the Vina project is copied into this repository; the binary is
used as published, unmodified.
