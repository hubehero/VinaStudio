# VinaStudio Packaging

This directory contains all scripts, templates, and resources needed to build
installable packages for VinaStudio on Linux and Windows.

## Directory Structure

```
packaging/
├── ci/
│   ├── bump-version.py       # Synchronize version across all project files
│   ├── build-linux.sh        # Linux build + .deb + tarball
│   ├── build-windows.bat     # Windows build + Inno Setup installer
│   ├── generate_icons.py     # SVG → PNG/ICO icon conversion
│   └── verify-build.sh       # Smoke test for build output
├── linux/
│   ├── vinastudio.desktop     # XDG desktop entry
│   └── debian/
│       ├── control            # Debian package metadata
│       ├── postinst           # Post-install script (symlink, icon cache)
│       └── prerm              # Pre-remove script
├── windows/
│   ├── vinastudio.iss         # Inno Setup installer script
│   └── icon.ico               # (generated) Windows icon
├── pyinstaller/
│   └── hooks/                 # Custom PyInstaller hooks (if needed)
└── README.md                  # This file
```

## Prerequisites

### Linux

| Tool | Purpose | Install |
|------|---------|---------|
| Python 3.12 | Runtime | `sudo apt install python3.12 python3.12-venv` |
| pnpm | Frontend build | `npm install -g pnpm` |
| rsvg-convert or cairosvg | SVG → PNG | `sudo apt install librsvg2-bin` or `pip install cairosvg` |
| dpkg-deb | .deb packaging | `sudo apt install dpkg` |
| PyInstaller | Bundling | `pip install pyinstaller` (installed by build script) |

### Windows

| Tool | Purpose | Install |
|------|---------|---------|
| Python 3.12 | Runtime | [python.org](https://python.org) |
| pnpm | Frontend build | `npm install -g pnpm` |
| Inno Setup 6.3+ | Installer creation | [jrsoftware.org](https://jrsoftware.org/isdl.php) |
| PyInstaller | Bundling | `pip install pyinstaller` (installed by build script) |
| cairosvg + Pillow | SVG → ICO | `pip install cairosvg Pillow` |

## Building Locally

### Linux

```bash
# From the repository root:
bash packaging/ci/build-linux.sh
```

This will:
1. Create a clean `.venv-build` virtual environment
2. Install all dependencies including PyInstaller
3. Build the Vue 3 frontend via `scripts/build_web.py`
4. Bundle with PyInstaller (`--onedir`, `--windowed`)
5. Convert the SVG icon to PNG (512x512)
6. Assemble a `.deb` package in `dist/`
7. Create a `.tar.gz` archive in `dist/`

Output:
- `dist/vinastudio-X.Y.Z-linux-amd64.tar.gz`
- `dist/vinastudio_X.Y.Z_amd64.deb`

### Windows

```cmd
REM From the repository root:
packaging\ci\build-windows.bat
```

This will:
1. Create a clean `.venv-build` virtual environment
2. Install all dependencies including PyInstaller
3. Build the Vue 3 frontend
4. Bundle with PyInstaller
5. Generate `icon.ico` from SVG (if missing)
6. Run Inno Setup Compiler to create the installer

Output:
- `dist\vinastudio-X.Y.Z-setup.exe`

### Windows in CI

`windows-latest` cannot push a release, but it can build the package:
`.github/workflows/windows-build.yml` (manual dispatch) produces
`vinastudio-<version>-setup.exe` (~219 MB) and uploads it as the
`windows-installer` artifact. It checks that the engine binary is inside the bundle
and runs there before compiling the installer, because that is the one thing a
Windows package has to get right.

Installer screens are **English only**: Inno Setup does not ship a Chinese language
file and the unofficial set upstream has none either. The application itself is
bilingual. Three other things this path needed, none of which had ever been built:
`vina` is excluded from the dependency graph on Windows (no wheel exists), the icon
generator renders through QtSvg instead of cairo (`libcairo-2.dll` does not exist
on Windows), and the `.iss` path prefixes were one level short.

## What the bundle carries

The desktop packages ship the **official Vina binary** alongside the Python
application, at `vinastudio/resources/vina/`. `packaging/pyinstaller/vinastudio.spec`
already copies the whole `resources/` tree, so the build just has to fetch it first
(`scripts/fetch_vina_cli.py`, checksum-verified) — the Linux release job does that
before running PyInstaller.

Why it is there on Linux too, where the `vina` Python module normally works: a
machine whose module is missing or broken can still dock, which is the whole point
of the command-line backend. On Windows there is no module to fall back on at all.

The binary is Apache-2.0 and its attribution travels with it
(`vinastudio/resources/vina/README.md`). It is **not** in the wheel: that is for
`pip` users on platforms where the module exists. The Windows installer additionally
needs the Microsoft Visual C++ runtime, which `packaging/windows/vinastudio.iss`
declares.

## Creating a Release

### 1. Bump the version

```bash
# Set a specific version:
python packaging/ci/bump-version.py --version 0.2.0

# Or read from pyproject.toml (if already updated):
python packaging/ci/bump-version.py
```

This updates version strings in:
- `pyproject.toml` (canonical source)
- `vinastudio/__init__.py` (if hardcoded fallback exists)
- `vinastudio/config.py` (if APP_VERSION is hardcoded)
- `web/package.json`
- `packaging/linux/debian/control`
- `packaging/windows/vinastudio.iss`

### 2. Commit and tag

```bash
git add -A
git commit -m "release: v0.2.0"
git tag v0.2.0
git push origin main --tags
```

### 3. Build on each platform

Run the appropriate build script on Linux and Windows. The version is read
automatically from `pyproject.toml`.

### 4. Verify the build

```bash
bash packaging/ci/verify-build.sh
```

### 5. Create a GitHub Release

Upload the following artifacts to a GitHub Release:
- `vinastudio-X.Y.Z-linux-amd64.tar.gz`
- `vinastudio_X.Y.Z_amd64.deb`
- `vinastudio-X.Y.Z-setup.exe`

## Icon Generation

To regenerate platform icons from the source SVG:

```bash
pip install cairosvg Pillow
python packaging/ci/generate_icons.py
```

Source: `vinastudio/desktop/assets/icon.svg`
Output:
- `packaging/linux/vinastudio.png` (512x512)
- `packaging/windows/icon.ico` (multi-resolution: 16, 32, 48, 64, 128, 256)

## CI Integration

The build scripts are designed to run in GitHub Actions. See
`.github/workflows/` for workflow definitions. The scripts:

- Read version from `pyproject.toml` (no manual intervention needed)
- Create isolated virtual environments (no pollution of CI runner)
- Produce self-contained artifacts ready for release upload

Two workflows matter beyond the tag build:

- **`release.yml`** — runs `packaging/ci/release-preflight.py` before anything is
  built, so a release that breaks the project's own rules cannot ship. See
  `RELEASING.md` for the rules themselves.
- **`engine-check.yml`** — because this tree ships no test suite, it docks the 1iep
  gold standard on **both** `ubuntu-latest` and `windows-latest`. The Windows job is
  the standing evidence that the engine works there (and that `vinastudio.core`
  imports without Qt or FastAPI), which is the claim the CLI backend exists to make
  possible.
