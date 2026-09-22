# Architecture

VinaStudio is four layers with strict boundaries. This document explains the
design and, more importantly, the three constraints that shape all of it.

For methodology validation, reproducibility, and references, see
[ACADEMIC_VERIFICATION.md](ACADEMIC_VERIFICATION.md).

```
┌──────────────────────────────────────────────────────────────┐
│ Qt main thread                                               │
│   QMainWindow · native menus · QWebChannel bridge            │
│   ┌────────────────────────────────────────────────────┐     │
│   │ QWebEngineView (Chromium)                          │     │
│   │   Vue 3 SPA · Element Plus · 3Dmol.js              │     │
│   └────────────────────────────────────────────────────┘     │
├──────────────────────────────────────────────────────────────┤
│ Background thread                                            │
│   Uvicorn + FastAPI on 127.0.0.1:<ephemeral>                 │
│   REST /api/*  ·  WebSocket /ws  ·  StaticFiles (SPA)        │
├──────────────────────────────────────────────────────────────┤
│ Spawned child processes (multiprocessing, start method spawn) │
│   Vina docking · Meeko parameterisation · grid generation     │
└──────────────────────────────────────────────────────────────┘
```

| Layer | Location | May import |
|---|---|---|
| Desktop shell | `vinastudio/desktop/` | PySide6, `config`, `logging_setup` |
| API server | `vinastudio/server/` | FastAPI, `core`, `schemas` |
| Domain core | `vinastudio/core/` | vina, meeko, rdkit, numpy — **never** Qt or FastAPI |
| Interface | `web/` | nothing Python; talks HTTP + WebSocket |

`core` has no framework imports, which is what makes the science testable
without a display or an event loop.

---

## Constraint 1 — the interface is served over local HTTP, never `file://`

A Vite bundle is ES modules. Chromium refuses to load ES modules from `file://`
because the scheme has no origin, so `QWebEngineView.load(QUrl.fromLocalFile(…))`
yields a blank page with CORS errors in the console.

The shell therefore starts Uvicorn in a background thread bound to
`127.0.0.1` on port `0` (the kernel picks a free port), and points the view at
`http://127.0.0.1:<port>`. Port `0` plus the
`_PortReportingServer.startup` hook in `desktop/server_thread.py` is how the Qt
side learns which port it got.

Consequences worth knowing:

- **The API and the UI share an origin**, so no CORS configuration is needed in
  production. The middleware in `server/app.py` exists purely for the Vite dev
  server on port 5173.
- **SSRF surface is eliminated by construction**: the socket is bound to
  loopback, never `0.0.0.0`.
- `web/vite.config.ts` uses **hash history** routing, so deep links work whether
  the page came from `StaticFiles` or from Vite — no SPA fallback route needed.

## Constraint 2 — docking runs in spawned child processes

Two separate reasons force process isolation:

1. **Vina cannot be cancelled.** `Vina.dock()` is a single blocking call into
   C++ with no interruption mechanism. Terminating the hosting process is the
   only way to honour a Cancel button, so the docking loop must not share a
   process with the UI.
2. **`fork` is unsafe here.** The parent holds a live Qt event loop and an
   asyncio loop. `fork` copies both, and a child that touches either can
   deadlock. `multiprocessing.get_context("spawn")` is mandatory — on Linux the
   default start method is `fork`.

Progress is recovered from Vina's own stdout. The C++ layer prints
`Computing Vina grid ... done.`, `Performing docking (random seed: N) ...`, a
`0% .. 100%` progress bar and finally the `mode | affinity | rmsd l.b. |
rmsd u.b.` table. The worker redirects file descriptor 1 with `os.dup2` into its
job log, keeps a separate pipe for structured events, and forwards both to the
event hub, which fans them out over `/ws`.

`verbosity` is therefore not just a UI preference: at `verbosity=0` there is no
stdout to parse and progress reporting degrades to coarse stage transitions.

**One documented exception.** `POST /docking/score`, `/optimize` and
`/randomize` build their affinity maps and run inside the API process, so they
are neither cancellable nor isolated. They exist for interactive exploration of
a pose that already exists: each call is a single fast operation rather than a
full docking run, and the interface awaits the response. They also compute their
own maps, which is why they reject scoring functions that cannot do that (`ad4`
needs externally generated AutoGrid4 maps). Anything longer belongs in
`/docking/start`.

## Constraint 3 — PDBQT is never rendered directly

3Dmol.js `addModel(data, format)` accepts `pdb`, `sdf`, `xyz`, `pqr`, `mol2`,
`cif`, `mmtf`, `gro`, `prmtop` and `cube`. **PDBQT is not among them.** Stripping
the extra columns to fake a PDB would be worse than useless: PDBQT has no bond
orders and omits non-polar hydrogens, so the renderer would guess connectivity.

The supported path is the one the AutoDock authors recommend:

- **Ligands and poses** → Meeko writes a `REMARK SMILES` line into every PDBQT
  it produces. `mk_export` / `RDKitMolCreate.from_pdbqt_mol` re-instantiates an
  RDKit molecule from that SMILES and copies the docked coordinates onto it,
  giving an SDF with the original bond orders and formal charges. 3Dmol renders
  the SDF.
- **Receptors** → `Polymer` / `mk_prepare_receptor.py` can write the receptor
  back out as PDB, which 3Dmol does render (and which cartoon styling needs).

This is also why the app can claim a "format conversion" feature honestly
instead of shipping a bond-order guesser.

---

## Request and event flow

```
        web (Vue)                        Qt process
           │                                  │
   user action                             │
           ├──── HTTP /api/… ───────► FastAPI router
           │                            │  validate (pydantic)
           │                            │  dispatch
           │                            ▼
           │                     spawn worker process
           │                            │  vina / meeko
           │                            │  structured events ─┐
           │                            │  stdout → job log   │
           │◄──── WS /ws ───────────────┴─────────────────────┘
           │
   reactive store update → 3Dmol re-render
```

Native capabilities that HTTP cannot provide — file dialogs, saving a PNG to a
chosen path, revealing a folder — go over **QWebChannel** instead. The bridge
object is published as `bridge` and reached from `web/src/api/bridge.ts`, which
resolves to `null` in a plain browser so the interface degrades instead of
breaking.

The reverse direction uses a small JavaScript namespace: the native menu calls
`window.vinastudio.<command>(...)`, registered in `web/src/api/native.ts`. The
interface stays the single source of truth for language and application state,
which is why the Qt menu LANGUAGES action asks the web layer to switch rather
than switching on its own.

---

## Molecule Manager

The Molecule Manager (`/molecules`) is a standalone view accessible from the
sidebar, providing a unified interface for uploading, inspecting, and preparing
molecule files. It replaces the previous per-panel (Receptor/Ligand) approach
with a single file-cabinet-style layout.

### Layout

```
┌──────────────────────────────────────────────────────────┐
│ MoleculeManagerView                                       │
│ ┌──────────────┬─────────────────────────────────────────┐│
│ │ MoleculePanel│  DetailPanel (flex-1)                    ││
│ │ (340–400px)  │  ┌─ vs-card ──────────────────────────┐ ││
│ │              │  │  header: name + type pill            │ ││
│ │ ┌──────────┐ │  │  ┌─ ViewportCanvas ──────────────┐ │ ││
│ │ │UploadBtn │ │  │  │  3D preview (PDB or SDF)      │ │ ││
│ │ │+ hint    │ │  │  └───────────────────────────────┘ │ ││
│ │ └──────────┘ │  │  facts (atoms/residues/chains...)   │ ││
│ │ ┌──────────┐ │  │  notes (warnings)                   │ ││
│ │ │Receptors │ │  │  SMILES block                       │ ││
│ │ │  ● 1iep  │ │  │  error alert                        │ ││
│ │ ├──────────┤ │  │  report (atoms → output, chips)     │ ││
│ │ │Ligands   │ │  │  actions [inspect][prepare][remove] │ ││
│ │ │  ● imat. │ │  └────────────────────────────────────┘ ││
│ │ ├──────────┤ │                                         ││
│ │ │Unknowns  │ │                                         ││
│ │ └──────────┘ │                                         ││
│ │ [Samples]    │                                         ││
│ └──────────────┴─────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────┘
```

### Stores and data flow

`useMoleculeStore` (`web/src/stores/molecules.ts`) manages all molecules:
- `molecules: MoleculeItem[]` — the central list
- `activeId` — currently selected molecule
- `receptors / ligands / unknowns` — computed by `getEffectiveType()`
- `receptorPath / ligandPath` — first prepared/inspected of each type
- `filters / samples` — loaded from backend on mount

Each `MoleculeItem` tracks its own state machine:
```
uploaded → inspecting → inspected → preparing → prepared
                ↓                      ↓
              error                  error
```

File loading follows two paths:
- **Desktop** (`pickFiles`): native dialog returns filesystem paths; backend
  reads in place; `addFromPath()` + `inspectMolecule()` auto-detects type.
- **Browser** (`pickFileForUpload`): `<input type="file">` → `uploadAndAdd()`
  → POST to `/api/files/upload` → workspace copy.

### UI patterns used

The Molecule Manager uses the same design system as all other panels:
- `vs-card` / `vs-card__header` / `vs-card__body` for card containers
- `facts` / `facts__row` / `facts__label` for property rows
- `report` / `report__title` / `chips` / `transforms` for preparation results
- `StatusPill` (inline `.pill` implementation) for status indicators
- `vs-mono` / `vs-mono-block` for monospaced content
- `notice` / `el-alert` for warnings and errors
- `el-collapse` / `el-tag` for samples and options

### Drag-and-drop

The left panel accepts file drops. A dashed blue border overlay appears during
drag-over. Dropped files are uploaded and auto-inspected.

---

## Rendering and scientific honesty

| Concern | Approach |
|---|---|
| Protein representation | 3Dmol cartoon from receptor PDB, sticks for pocket residues |
| Surfaces | 3Dmol `addSurface` with the VDW/SAS/SES types the interface exposes |
| Search box | Twelve edges drawn as lines with Vina's semantics (centre + edge lengths) |
| Interactions | Computed geometrically in Python (distances and angles), drawn as dashed cylinders |
| Electrostatic potential | Coulomb sum over PDBQT partial charges onto a grid, written as a Gaussian cube — **labelled as a point-charge approximation, never as a QM ESP** |

Anything the application cannot do correctly is stated in the UI rather than
approximated silently. The clearest example is AutoDock4 scoring: it needs
affinity maps produced by AutoGrid4, which is not bundled, so the capability
matrix marks `ad4` as `nativeMaps: false` and neither docking form offers it —
there is no way to supply maps yet, and an option that can only fail is worse
than an absent one. `/docking/score`, `/optimize` and `/randomize` refuse it for
the same reason.

---

## Roadmap

| Phase | Scope | State |
|---|---|---|
| 0 | Desktop shell, loopback API, WebSocket channel, bilingual UI, environment self-check, WebGL viewport | done |
| 1 | PDBQT parsing; Meeko ligand preparation (MOL/SDF/MOL2 -> PDBQT); receptor preparation; PDBQT -> SDF/PDB export; native file pickers and upload fallback; prepared molecules rendered | done |
| 2 | Search-box editor with autobox; receptor/ligand styling controls; surface rendering | done |
| 3 | Spawned job system with live progress, log streaming and real cancellation; full scoring/optimization parameter surface | done |
| 4 | Pose ranking, energy decomposition, interaction detection, electrostatic cube, export | done |
| 5 | Batch virtual screening, `.vinaproj` project files | done |
| 6 | PyInstaller packaging | next |

### Artefacts and the `/artifacts` mount

Every preparation run gets its own directory under `~/.vinastudio/workspace`
(`core/paths.py`), and the API returns artefact URLs rather than file contents.
A prepared receptor's PDB is around 350 kB, which has no business travelling
inside a JSON response; the interface fetches it when the renderer needs it, and
the same directory is where docking jobs will write their output.

The mount exposes only that workspace, and `StaticFiles` refuses traversal, so
it cannot reach anything the application did not write.

### Two problems the receptor pipeline has to solve first

**Residues split across the file.** Meeko's parser assumes a residue's atoms are
contiguous. The official 1iep reference has a single `HB2` of `SER A 438` on its
second line and the rest of that residue near the end, which makes Meeko 0.8
reject the whole structure with "interrupted residues". `normalise_pdb_atom_order`
regroups each residue around its largest contiguous block — a chemical no-op that
preserves residue order — and the result then matches upstream's own PDBQT atom
for atom.

**Points of departure from upstream.** Our receptor is not byte-identical to the
one upstream ships, and the difference is worth knowing: Meeko now types
methionine thioethers and cysteine thiols as `S` where the older version used
`SA`, with charges of about -0.79 instead of -0.10. Element counts, coordinates
and every other atom type match exactly. The test pins the magnitude so a further
change cannot pass unnoticed, and confirming the scoring impact is a Phase 3
task.


## Dependencies worth pinning deliberately

- **`meeko >= 0.7.1`** — 0.5/0.6 declare `requires_python <3.12`, so they cannot
  be installed on this project's Python 3.12.
- **`gemmi`** — Meeko 0.8.0 imports `gemmi` from `chemtempgen` but its PyPI
  metadata declares no dependencies at all, so it must be listed explicitly or
  `import meeko` fails.
- **`typescript` 5.x in `web/`** — TypeScript 7 no longer ships `lib/tsc`, which
  `vue-tsc` requires. TypeScript is only used for type checking; Vite strips
  types itself, so pinning to 5.x costs nothing.
