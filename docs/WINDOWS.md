# VinaStudio on Windows

**English** · [简体中文](WINDOWS.zh-CN.md) · [Home](../README.en.md)

> **Status (2026-10-20).** The Windows desktop build has been walked through on a
> real Windows machine, and the installer is built by CI. It ships publicly with
> **0.4.0**; 0.3.0 and earlier have no Windows asset.
>
> This page covers what is supported, what works, where the boundaries are, and
> how to diagnose a problem. The scientific conventions — energies are not
> comparable across scoring functions, PDBQT has no bond orders, and so on — are
> the same as on Linux; see the [User Guide](USER_GUIDE.md).

---

## 1. Scope

| Item | Requirement / note |
|---|---|
| Operating system | Windows 10 1809 (build 17763) or newer, or Windows 11 |
| Architecture | x64 (ARM64 is not supported) |
| Installation | Inno Setup installer; per-machine into `C:\Program Files\VinaStudio`; **administrator required** |
| Installer size | about 230 MB |
| Graphics | A Direct3D 11 GPU (Intel, NVIDIA or AMD); WebGL goes through ANGLE onto D3D11 |
| Docking engine | The bundled **AutoDock Vina 1.2.7 command-line binary** (Apache-2.0) |
| Availability | **From 0.4.0**; the build produced from the current development tree has passed the real-machine walkthrough |
| Code signing | **Unsigned**, so SmartScreen asks for confirmation on first run (see §2) |

The installer carries the Python runtime, the scientific stack and the Vina
engine. **Users do not need Python, uv, Node.js or pnpm.**

---

## 2. Installing

1. Download `vinastudio-<version>-setup.exe` from the
   [releases page](https://github.com/hubehero/VinaStudio/releases) and check the
   SHA-256 shown there.
2. Run it. The installer is not code-signed, so SmartScreen may say “Windows
   protected your PC”; choose **More info → Run anyway**.
3. The installer checks for the VC++ 2015–2022 x64 runtime and points to
   Microsoft's download if it is missing. The bundle also carries a copy of the
   runtime DLLs, but the system runtime is still the recommended setup.
4. Launch from the Start menu or the desktop shortcut. The first launch asks you
   to choose a workspace directory.
5. The installer UI is English only (Inno Setup does not ship a Simplified
   Chinese language file); the application itself is bilingual.

Silent installation, for deployment scripts:

```powershell
vinastudio-0.4.0-setup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART
```

---

## 3. What works

The Windows build carries the same application as the Linux build:

- receptor and ligand preparation (PDB, mmCIF, MOL, SDF, MOL2, SMILES, the
  built-in 2D sketcher);
- binding-box definition, candidate-site detection and per-site ranking;
- single-ligand docking, batch docking and virtual screening, with live
  progress, streamed logs and real cancellation;
- Vina and Vinardo scoring; AutoDock4 needs external maps (see §4.1);
- pose ranking, geometric validation, redocking RMSD, clustering, interaction
  fingerprints and 2D interaction diagrams;
- job history, project save/restore, CSV, HTML and result-bundle export;
- bilingual UI, light and dark themes, environment self-check and renderer
  diagnostics.

### The docking backend: `vina-cli`

Upstream publishes **no Windows build of the `vina` Python module** — PyPI has
manylinux wheels only, and conda-forge builds it for Linux and macOS. The Windows
application therefore uses the bundled `vina.exe` automatically:

- it is the same AutoDock Vina **1.2.7** engine, with the same parameters as the
  Python API; with a fixed seed the two agree pose for pose on 1iep;
- the environment page names the backend `vina-cli` with the reason
  `module-missing`. The dependency table still says that importing `vina` fails —
  that is a fact — but the capability verdict is “ready to dock”. Failing to
  import and failing to dock are different questions;
- interactive **score / optimise / randomise** use the same binary.

---

## 4. Known boundaries

### 4.1 AutoDock4 (`ad4`) needs external maps

As on Linux: the project does not ship `autogrid4`, so `ad4` can only score with
**maps generated elsewhere**. The interface marks `ad4` as `nativeMaps: false`,
and interactive scoring/optimisation/randomisation refuse it. Vina and Vinardo
are unaffected.

### 4.2 Antialiasing is off by default

QtWebEngine 6 on Windows has a known, intermittent WebGL compositor flicker, and
3Dmol's antialiasing path doubles the draw buffer (four times the pixels), which
makes it worse. **Antialiasing is therefore off by default**:

- to restore smooth edges: Settings → Rendering quality → turn off “Force
  antialiasing off”;
- if the flicker returns, it is the upstream compositor issue, not the docking
  calculation;
- the default applies on every platform; older settings migrate once, and an
  explicit choice sticks afterwards.

### 4.3 Unsigned installer, no auto-update

- SmartScreen prompts on first run because the installer is unsigned.
- The application does not check for updates; install a newer package over the
  old one.
- The installer is per-machine (`Program Files`) and needs administrator rights;
  uninstall through “Apps & features”.

### 4.4 The installer UI is English

The application is bilingual; only the installer's few screens are English
(Inno Setup does not ship a Simplified Chinese language file).

### 4.5 Platform coverage

- x64 only; Windows ARM64, Windows 7 and Windows 8 are not supported.
- macOS has a source-only path — no package and no release-level verification.
- The real-machine walkthrough currently covers one Intel UHD (D3D11) machine;
  other GPU and driver combinations have not been checked one by one. The
  environment page shows the actual renderer, so include that string in a bug
  report.

### 4.6 Interactive operations are synchronous

Score, optimise and randomise run through the command-line binary on Windows, so
the request waits for the calculation to finish (the Linux Python API call is
blocking in the same way). Docking jobs themselves still run in a child process,
can be cancelled, and do not block the interface.

### 4.7 Network and files

- The application listens on loopback only and opens no external port. Fetching a
  conformer by name from PubChem needs internet access.
- Uploads are limited to 100 MB by default (`VINASTUDIO_MAX_UPLOAD_MB`).
- Non-ASCII paths work; 0.4.0 fixes the ligand-read failure that affected them.

### 4.8 The science is unchanged

Energies from different scoring functions are **not comparable**; a predicted
affinity is not an experimental binding free energy; PDBQT keeps heavy atoms and
polar hydrogens only, so the atom count legitimately drops. None of this depends
on the operating system.

---

## 5. Troubleshooting

| Symptom | What to do |
|---|---|
| Docking stays at 0% with near-zero CPU | Fixed in 0.4.0 (the frozen-process start-up defect). Confirm you are on 0.4.0+ and check the SHA-256 |
| A black `vina.exe` console window appears during a run | Fixed in 0.4.0; only older packages show it |
| The 3D viewport flickers irregularly | Keep “Force antialiasing off” enabled (the default). If you enabled AA, the flicker is the upstream QtWebEngine compositor issue |
| The viewport is slow | Check Environment → actual renderer. `SwiftShader` or `Basic Render Driver` means software rendering. Try `VINASTUDIO_SOFTWARE_RENDER=1` as a comparison |
| A ligand under a non-ASCII path fails to load | Fixed in 0.4.0; older packages return 500 |
| The installer reports a missing VC++ runtime | Install Microsoft's VC++ 2015–2022 x64 runtime |

**Log:** `%USERPROFILE%\.vinastudio\logs\vinastudio.log`
**Workspace config:** `%USERPROFILE%\.vinastudio\workspace.json`

**Read-only diagnostics** (from the release repository,
`packaging/windows/vinastudio-diagnostics.ps1`): start the application, then run

```powershell
powershell -ExecutionPolicy Bypass -File .\vinastudio-diagnostics.ps1
```

It reports the GPU model, driver version, OS build, installer SHA-256, a copy of
the log, and live `/api/system/info` and `/api/system/selfcheck` JSON. It needs no
administrator rights.

---

## 6. Verification record

- Real-machine walkthrough: 2026-10-20, Windows with an Intel UHD GPU
  (ANGLE / D3D11). Preparation, docking, analysis, persistence, non-ASCII paths
  and renderer diagnostics all behaved as expected.
- Development-tree installer used for the walkthrough: `vinastudio-0.3.0-setup.exe`,
  229,564,630 bytes, SHA-256
  `ec51d3d5e8448b2ab65b4a8a02dc88c25175e86aac80dac1ae81f2c9370bbb66`.
- **0.4.0 release installer**: `vinastudio-0.4.0-setup.exe`, 229,571,859 bytes,
  SHA-256 `63722aca9e5566e5bc0a285aa98093e1d3ec088cc219539739b3154b5e64cd9f`,
  built from tag `v0.4.0` (`18a6722`). It carries the same application code as the
  walkthrough build; the version and documentation are the only differences.
- Every Windows build docks 1iep once inside the frozen bundle (exhaustiveness 1)
  and asserts completion, at least one pose and a negative affinity. The 0.4.0
  build: `-8.593 kcal/mol` in 15.31 s (run `39544666349`). That covers process
  spawn, stdout redirection, the CLI backend and the bundled engine.
- The Linux artifacts for the same tag were built by run `39545746608`.
