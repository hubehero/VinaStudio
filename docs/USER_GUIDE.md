# VinaStudio User Guide

**English** · [简体中文](USER_GUIDE.zh-CN.md) · [Home](../README.en.md)

This guide takes you from a fresh installation to a docked pose you can trust:
prepare a receptor and a ligand, choose the search box, run AutoDock Vina, read
the result, and export it. It assumes no command-line experience.

If you only want the short version, the [quick reference](#quick-reference) at
the end lists every step in order.

---

## 1. What VinaStudio is

VinaStudio is a desktop workbench around **AutoDock Vina** (the 1.2.7 engine).
It handles the whole docking workflow — PDBQT preparation, box definition,
docking, pose inspection, interaction analysis and export — without asking you to
assemble command lines by hand.

The interface is bilingual (Chinese and English), and the scientific results are
computed by Vina itself; the application never invents a score.

**Where to go next**

- Windows installation and boundaries: [WINDOWS.md](WINDOWS.md)
- How the application is put together: [ARCHITECTURE.md](ARCHITECTURE.md)
- What changed in this version: [CHANGELOG.md](../CHANGELOG.md)

---

## 2. Before you install

### 2.1 Requirements

| Item | Requirement |
|---|---|
| Operating system | Linux (x86_64), Windows 10 1809+ / 11 (x64), or macOS from source |
| Python | 3.12 — **source installs only**; the Windows installer bundles it |
| Package manager | [uv](https://docs.astral.sh/uv/) for source installs |
| Node.js | 22+ and [pnpm](https://pnpm.io/), to build the interface and run frontend tests |
| Memory | 4 GB minimum; more for large receptors |
| Disk | About 2 GB with all dependencies |

### 2.2 Windows: use the installer

Download `vinastudio-<version>-setup.exe` from the
[releases page](https://github.com/hubehero/VinaStudio/releases), verify its
SHA-256, and run it. The installer needs administrator rights and is unsigned, so
SmartScreen asks for confirmation. It includes Python, the scientific stack and
the Vina engine — you do **not** need to install Python, uv, Node.js or pnpm.

The full Windows scope and its boundaries are in [WINDOWS.md](WINDOWS.md).

### 2.3 Linux: use a package or the source tree

Published releases provide a `.deb` for Ubuntu/Debian and a portable `.tar.gz`.
Unpack the tarball and run `vinastudio/vinastudio`; install the `.deb` with your
package manager.

To run the development tree instead:

```bash
uv sync --extra dev
pnpm -C web install
pnpm -C web build
uv run python -m vinastudio
```

`scripts/build_web.py` wraps the two pnpm steps. The bundled Linux packages
already contain the built interface and the Vina binary.

---

## 3. First launch

1. Start VinaStudio from the Start menu, the desktop shortcut, or
   `uv run python -m vinastudio` on a source install.
2. The first launch asks for a **workspace** — a folder where prepared files,
   jobs and exports are kept. Choose a normal local folder; the application
   creates `projects/`, `receptors/`, `ligands/`, `jobs/` and `exports/` inside it.
3. The workspace can be changed later in **Settings → Workspace**.

The status bar shows the application version and the event channel. A green
“connected” indicator means the interface and the local API are talking; both
run on your machine, and the API listens on loopback only.

> **Windows note:** the first run may be slow while the bundled runtime
> initialises. Later launches are faster.

### 3.1 Checking for updates

Open **Settings → General** and choose **Check for updates**. VinaStudio asks
GitHub Releases only when you click; it reports the latest version and, if a
newer release exists, opens the official release page. It never downloads or
installs anything. An offline or rate-limited check shows a message and leaves
the app unchanged.

---

## 4. The interface

The left sidebar is the workflow: **Workbench**, **Molecules**, **Binding
sites**, **Docking**, **Reports**, **Batch screening**, **Virtual screening**,
**History**, **Environment**, **Help** and **About**.

The 3D viewport is the centre of the work. Drag to rotate, scroll to zoom, and
use the toolbar to re-frame the view or export a PNG. The right-hand panel
changes with the page: preparation options, box coordinates, docking parameters,
or result details.

The **Workbench** page is the best starting point. It shows the pipeline steps,
marks what is ready, and offers a one-click 1iep example if you want to see a
complete run before using your own structures.

---

## 5. Prepare a receptor

A receptor is the protein you dock into. VinaStudio accepts PDB and mmCIF files.

1. Open **Molecules** and load your receptor file.
2. The manager inspects the file and proposes a type. If it guesses wrong, set it
   to **Receptor** explicitly.
3. Open the preparation options. The defaults remove waters and non-polymer
   groups; keep them unless you have a reason not to. Flexible side chains can be
   picked here as well.
4. Run the preparation. The result is a **PDBQT** file — the format Vina reads.
5. Check the summary: residue and atom counts, any ignored residues, and the
   warnings. A drop in atom count is expected: PDBQT keeps heavy atoms and polar
   hydrogens only.

If Meeko rejects residues because their atoms are split across the file, the
application offers to normalise the atom order and retry. This changes nothing
chemically.

---

## 6. Prepare a ligand

A ligand is the small molecule you are docking. VinaStudio accepts MOL, SDF,
MOL2 and PDB files, and can also build a ligand from SMILES or from the built-in
2D sketcher.

1. Load the ligand in **Molecules**.
2. Inspect it: atom count, rotatable bonds, whether it has 3D coordinates and
   hydrogens. A 2D structure is fine — preparation will embed and protonate it.
3. Choose the preparation options. The defaults are suitable for most drug-like
   molecules; macrocycle and amide settings are there when you need them.
4. Run the preparation. VinaStudio writes a PDBQT and an SDF copy; the SDF is what
   the 3D viewport draws.
5. Check the report: hydrogens added, conformer generated, rotatable bonds found,
   total charge and atom types.

Both the receptor and the ligand become the **pipeline** molecules. The docking
page uses them unless you pick different ones in the molecule selectors.

---

## 7. Define the search box

The box is the region Vina searches. It should contain the binding site and a
little surrounding space, but not the whole protein.

There are three ways to set it:

- **From a ligand** — if you have a co-crystal ligand, choose it and the box is
  fitted around it.
- **From residues** — pick the residues that line the site.
- **Manually** — type the centre and edge lengths.

The box is drawn in the viewport and can be moved with Shift-drag. A 20 Å box is
a reasonable default for a drug-like ligand; smaller boxes dock faster but may
cut off a pose.

**Binding sites** can also propose candidates from the receptor geometry alone.
That is a coarse screen for choosing where to look, not a claim about the true
site; see the in-app glossary and the honesty notes on the page.

---

## 8. Run docking

Open **Docking**, confirm the receptor, ligand and box, then set:

| Parameter | What it does |
|---|---|
| Scoring function | Vina (default), Vinardo, or AutoDock4 with external maps |
| Exhaustiveness | Search effort; higher is slower and more thorough |
| Number of poses | How many poses to keep |
| Energy range | Keep poses within this energy of the best one |
| Seed | Makes a run reproducible when the engine supports it |
| CPU | Threads to use; 0 means all available |

Press **Run**. The job starts in a separate process, so the interface stays
responsive; progress and the engine log stream into the panel, and **Cancel**
actually stops the run by terminating that process.

Docking time depends on the box, the ligand and the exhaustiveness. A small
1iep run takes seconds; a large box with high exhaustiveness can take minutes.
The time is shown when the job finishes.

---

## 9. Read the result

The result page ranks poses by predicted affinity. The most negative value is the
best-scoring pose, in kcal/mol.

- **Affinity** is a scoring-function estimate, not an experimental binding free
  energy. Do not compare values from different scoring functions.
- **RMSD (lower/upper bound)** describes how different a pose is from the best
  one.
- The **3D viewport** draws the selected pose with the receptor. Pose navigation
  swaps the ligand without moving your camera.
- The **analysis** panels add geometric validation, redocking RMSD against a
  reference, clustering and interaction detection. These are report-only: they
  never re-dock or edit coordinates.
- **Interactions** are shown for the pose you selected, using geometric cutoffs
  for ionic contacts, hydrogen bonds and hydrophobic contacts. The 2D diagram
  gives the same contacts as a readable map.

**Export** provides CSV, a self-contained HTML report, and a result bundle. The
report records the parameters the run actually used, so it can be pasted into a
methods section without guessing.

---

## 10. Advanced workflows

- **Batch docking** — one receptor against a list of ligands, with a leaderboard
  and per-ligand rows.
- **Virtual screening** — import a library, dock each molecule, rank the hits,
  and resume if the run is interrupted.
- **Site screening** — dock one ligand into each candidate box and rank the
  boxes. This is a coarse comparison between candidates, not a production run.
- **Flexible docking** — select flexible side chains during receptor preparation;
  Vina then searches their torsions as well.
- **AutoDock4** — requires AutoGrid4 maps generated outside the application. The
  interface refuses `ad4` when no maps are supplied rather than silently running
  a different scoring function.

---

## 11. Frequently asked questions

**The interface is blank after switching pages.**
That was a known defect in older builds; update to the current release. If it
recurs, include the page and the log in a bug report.

**The 3D view is slow.**
Open **Environment** and read the actual renderer. `SwiftShader`, `llvmpipe` or
`Basic Render Driver` means software rendering. On Windows, antialiasing is off
by default because of an upstream QtWebEngine flicker; leave it off unless you
need smooth edges.

**Docking stays at 0% with no CPU use.**
That was a packaging defect fixed in 0.4.0. Confirm the version and check the
installer hash.

**A ligand fails to load from a folder with Chinese characters.**
Fixed in 0.4.0. Older builds returned an error from RDKit's path handling.

**Can I compare affinities from Vina and Vinardo?**
No. Different scoring functions produce different energy scales. Compare only
runs that used the same function.

**Why did the atom count drop after preparation?**
PDBQT keeps heavy atoms and polar hydrogens. Removing non-polar hydrogens is the
format's normal behaviour, not data loss.

**Can I reproduce a run exactly?**
Use a fixed seed for docking. Vina's `randomize` operation ignores the seed, so
that one cannot be replayed; the interface says so.

---

## 12. Glossary

- **Receptor** — the protein structure being docked into.
- **Ligand** — the small molecule being docked.
- **PDBQT** — AutoDock's structure format; heavy atoms plus polar hydrogens and
  atom types.
- **Box** — the search volume, defined by a centre and three edge lengths.
- **Pose** — one predicted binding conformation with its score.
- **Affinity** — the scoring function's estimate for a pose, in kcal/mol.
- **Exhaustiveness** — how much search effort Vina spends.
- **RMSD** — root-mean-square deviation between two poses, in ångström.

---

## Quick reference

1. Choose a workspace.
2. Load and prepare the receptor → PDBQT.
3. Load and prepare the ligand → PDBQT.
4. Set the box: from a ligand, from residues, or manually.
5. Open Docking, choose the scoring function and exhaustiveness, press Run.
6. Inspect the poses, interactions and validation.
7. Export CSV, HTML or a result bundle.

For installation problems, start with [WINDOWS.md](WINDOWS.md) on Windows and the
[CHANGELOG](../CHANGELOG.md) for version-specific fixes.
