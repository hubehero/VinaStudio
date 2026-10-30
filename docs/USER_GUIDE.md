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
   groups and allow residues that fail Meeko template matching (you can change
   that default in Settings, or switch it for this molecule only). To retain a
   structural water or metal, enter its residue key (for example `B:601`) in
   **Keep selected water/metal**. Flexible side chains can be picked here as
   well. Ignored residues are always listed in the report; allowing them does
   not make their bond orders or protonation modelled.
4. Run the preparation. The result is a **PDBQT** file — the format Vina reads.
5. Check the summary: residue and atom counts, any ignored residues, and the
   warnings. A drop in atom count is expected: PDBQT keeps heavy atoms and polar
   hydrogens only. The report lists every water/hetero group deleted or kept,
   HID/HIE/HIP histidine states, the altloc policy, and residues removed for
   altloc. Protonation and formal charges follow the input and Meeko templates;
   missing atoms/loops are not rebuilt. Those assumptions are shown in the
   report and in the Methods text for a single docking run.

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

### Online compound libraries

Open **Molecules → From Library**. The **RCSB PDB** tab searches structures and
co-crystal ligands. The **Compounds** tab searches PubChem or ChEMBL:

- **Name / ID** accepts a compound name, CID, ChEMBL ID, InChIKey or SMILES.
- **Similarity** and **Substructure** accept SMILES and use the provider's own
  chemical index; no local database is built or downloaded.
- Results are paged and carry their source and licence. The detail panel shows
  the 2D structure and properties.
- PubChem downloads a **3D** SDF. ChEMBL's public SDF is currently **2D**, so the
  interface says “Prepare first”; run the normal ligand preparation to generate
  a 3D conformer before docking.
- A source's score is only comparable within that source. Do not merge ChEMBL
  and PubChem scores.

The old **PubChem** tab remains as a quick single-compound fetch. RCSB and
PubChem data are free; ChEMBL data is CC BY-SA 3.0 and should be cited with its
source URL and release version. Commercial/registration-gated sources such as
DrugBank are not integrated.

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

**The box must be in the receptor's coordinate frame.** A box copied from a
different PDB entry can sit entirely outside the receptor; docking then has
nothing to score. VinaStudio refuses that request with “the docking box contains
no receptor atoms” instead of returning a page of zero-energy poses. Select the
receptor and ligand from the same complex, or recompute the box from the current
receptor/ligand.

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
responsive; the stage and engine log stream into the panel, and **Cancel**
actually stops the run by terminating that process.

Vina 1.2.7 does not expose a reliable live percentage: it prints a progress
scale at the end, and neither the Python API nor the CLI offers a per-step
callback. A single run therefore uses an **activity bar** and the stage text
(maps → docking → export) rather than inventing 0/50/100 values. Batch and
screening jobs do have real per-ligand completion counts and keep numeric
progress.

If you have several receptor conformers, enable **Ensemble conformers**, select
at least two prepared receptors and run. Each conformer is docked separately
with the same box; the result lists its best affinity and marks the winning
conformer. This is ensemble docking, not induced fit/IFD, and the conformers
must already share a coordinate frame.

Docking time depends on the box, the ligand and the exhaustiveness. A small
1iep run takes seconds; a large box with high exhaustiveness can take minutes.
The time is shown when the job finishes.

---

## 9. Read the result

The result page ranks poses by predicted affinity. The most negative value is the
best-scoring pose, in kcal/mol.

A completed calculation is not automatically a good binder. A best affinity of
**0.00** usually means no valid score was produced (check the receptor/box and
log); a **positive** affinity means the engine completed but predicts no
favourable binding. The interface flags both instead of showing a plain green
“completed”.

- **Affinity** is a scoring-function estimate, not an experimental binding free
  energy. Do not compare values from different scoring functions.
- **RMSD (lower/upper bound)** describes how different a pose is from the best
  one. Redocking RMSD compares the pose with the reference in the shared receptor
  frame without superposing the ligand; a pose moved to another site is not 0 Å.
- The **3D viewport** draws the selected pose with the receptor. Pose navigation
  swaps the ligand without moving your camera. **Overlay all poses** shows the
  first 20 poses in distinct colours (a visual comparison, not an alignment or
  an energy scale).
- The **analysis** panels add geometric validation, redocking RMSD against a
  reference, clustering and interaction detection. These are report-only: they
  never re-dock or edit coordinates.
- **Interactions** are shown for the pose you selected: ionic/salt-bridge
  candidates, hydrogen bonds, hydrophobic contacts, halogen bonds (a
  distance-only candidate), metal coordination and water-mediated contacts.
  Metals/waters must have been retained during receptor preparation. The 2D
  diagram gives the same contacts as a readable map; the residue summary groups
  them and the CSV export keeps the raw rows. There is no π-stacking.

**Export** provides CSV, a self-contained HTML report, and a result bundle. The
report records the parameters the run actually used, so it can be pasted into a
methods section without guessing.

Result bundles are written to the workspace's `exports/result-bundles/` folder
with a timestamped name, and the success message shows the absolute path. Use
the same folder when importing a bundle someone shared with you.

### 9.1 Importing a result bundle

Use **Import bundle** on the report page and choose a zip exported by
VinaStudio. The bundle is restored as a new read-only result in the current
workspace, with its poses, parameters and log; it never overwrites the current
project.

### 9.2 Searchable help

Open **Help** and search by symptom (preparation failure, missing files, AD4 maps,
no candidate site, failed jobs, Windows SmartScreen, flicker). Failure cards and
warnings link straight to the matching entry. Deeper references: `docs/USER_GUIDE.md`
and `docs/WINDOWS.md`.

### 9.3 Keyboard and undo

Press **Ctrl/Cmd+K** for the command palette (pages, settings, theme and language).
**Ctrl/Cmd+Z** undoes the last destructive action (delete a molecule, clear the
list, delete a saved view); deletions ask first. Press **?** for the full shortcut
list. Text fields keep their own Ctrl/Cmd+Z.

### 9.4 Organising results

**Results Search** supports favourites, tags, bulk tagging and saved filter
views. The index upgrades automatically; re-indexing a run keeps its tags and
favourite. Results load 50 at a time; press **Load more** for older runs, and a
new search or filter resets to the first page.

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

### Project files

A project is a `.vinaproj` JSON file containing the receptor/ligand references,
box, docking configuration and result references. The project manager stores
projects in the workspace's `projects/` folder.

- **Save** (`Ctrl+S`) overwrites the current project file. A new project is
  created in `projects/` first.
- **Save As** (`Ctrl+Shift+S`) opens the native file dialog, starts in
  `projects/`, and lets you choose both the folder and filename. The chosen name
  is stored in the project as its display name.
- Project writes are atomic; an interrupted save does not truncate the previous
  file. Only `.vinaproj` paths are accepted by Save As.

---

## 11. Frequently asked questions

### 11.1 Diagnose and repair

Open **Environment → Diagnose and repair** when a workspace, engine, dependency,
catalog or disk problem is suspected. The check is read-only and reports every
finding as **healthy**, **warning** or **error**, with the technical evidence and
a recommended action.

**Repair safe items** only creates missing application/workspace directories. It
never deletes molecules, poses, projects, job indexes or databases, and it does
not install packages or change the engine backend. Corrupt configuration,
catalog or job indexes are left in place so the evidence can be inspected; the
panel states the reason and the recovery action instead. Use **Copy report** to
attach the JSON to a support report. The local WebGL renderer is checked in the
page as well, but driver changes remain a user action.

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

**Docking is refused with “the docking box contains no receptor atoms”.**
The box and receptor are in different coordinate frames (often a box or ligand
taken from another PDB entry). Choose a receptor/ligand pair from the same
complex, then recompute the box; do not widen the box until it accidentally
touches the protein. A box with no receptor atoms would make Vina return
zero-energy poses that are not a docking result.

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
