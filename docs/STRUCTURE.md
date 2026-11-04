# Project Structure Map

**English** · [简体中文](STRUCTURE.zh-CN.md) · [Home](../README.en.md)

**Visual version:** [structure.html](structure.html), a full tree page. Open it in a browser; GitHub shows the HTML source rather than rendering this file.

This page uses text trees, tables and ordered steps. Start with the runtime shape, follow one docking job, then use the code tree and the Catalog relationships.

## How to read it

| Time | Read |
|---|---|
| 30 seconds | [Runtime shape](#runtime-shape): what shares a process |
| 5 minutes | [Docking lifecycle](#docking-lifecycle): requests, events and Cancel |
| Changing code | [Code map](#code-map): find a directory by responsibility |
| Changing Catalog | [Catalog relationships](#catalog-relationships): molecules, Studies, collections and libraries |

## Runtime shape

<details open>
<summary><strong>Desktop process (one Python process)</strong></summary>
<ul>
  <li><details open>
    <summary><strong>Qt main thread</strong>: window, interface and native capabilities</summary>
    <ul>
      <li><code>PySide6 shell</code>: main window, native menus</li>
      <li><code>QWebEngineView</code>: Vue 3 + 3Dmol.js</li>
      <li><code>QWebChannel</code>: file dialogs, save, reveal</li>
    </ul>
  </details></li>
  <li><details open>
    <summary><strong>Background thread</strong>: local API</summary>
    <ul>
      <li><code>FastAPI</code>: REST <code>/api/*</code> and WebSocket <code>/ws</code></li>
      <li><code>JobManager</code>: submit, events, cancel, restore</li>
      <li><code>EventHub</code>: broadcast job events to the SPA</li>
    </ul>
  </details></li>
</ul>
</details>

<details open>
<summary><strong>spawn child process</strong>: started per task</summary>
<ul>
  <li><code>worker.py</code>: stdout parsing, Pipe events</li>
  <li><code>AutoDock Vina 1.2.7</code> · <code>Meeko</code> · <code>RDKit</code></li>
</ul>
</details>

<details open>
<summary><strong>Workspace</strong>: the only persistence location</summary>
<ul>
  <li><code>jobs/</code>: artifacts, logs, <code>job.json</code></li>
  <li><code>projects/</code>: <code>.vinaproj</code> project files</li>
  <li><code>catalog.sqlite</code>: molecules, Studies, collections, libraries</li>
</ul>
</details>

Key points:

- The Qt main thread and the FastAPI background thread share one desktop process. The API is not a separate service.
- Docking runs in a spawned child process. Vina has no cancellation API, so Cancel terminates all workers for that job.
- The web layer reaches Python over HTTP and WebSocket; native file operations use QWebChannel.
- RCSB, PubChem and ChEMBL are optional external sources reached from the API, not part of the local structure.

## Docking lifecycle

1. Vue calls `POST /api/docking/start` and receives a job id immediately.
2. JobManager starts a spawn worker and assigns an event Pipe.
3. The worker calls Vina/Meeko; stdout is redirected to the job log.
4. Structured events travel Pipe → JobManager → EventHub → WebSocket → UI.
5. Completion writes `job.json` and artifacts; Cancel terminates all workers for that job.

A single docking run normally uses one worker. Batch and screening runs start several workers by shard, each with its own event pipe.

## Code map

<details open>
<summary><strong>vinastudio/</strong> · Python application</summary>
<ul>
  <li><details open>
    <summary><code>desktop/</code>: Qt shell, native menus, QWebChannel, server thread</summary>
    <ul>
      <li><code>main_window.py</code>: window and menu commands</li>
      <li><code>server_thread.py</code>: background Uvicorn and port reporting</li>
      <li><code>bridge.py</code>: native file bridge</li>
    </ul>
  </details></li>
  <li><details open>
    <summary><code>server/</code>: FastAPI, JobManager, WebSocket, routers</summary>
    <ul>
      <li><code>app.py</code>: application assembly, static SPA, error mapping</li>
      <li><code>job_manager.py</code>: spawn, Pipe, cancel, restore</li>
      <li><code>ws.py</code>: EventHub and <code>/ws</code> broadcast</li>
      <li><code>routers/</code>: system, files, catalog, docking, screening, ...</li>
    </ul>
  </details></li>
  <li><details open>
    <summary><code>core/</code>: preparation, docking, analysis; no Qt or FastAPI dependency</summary>
    <ul>
      <li><code>chem/</code>: receptor/ligand preparation, PDBQT, export, interactions, sketcher</li>
      <li><code>catalog/</code>: SQLite Catalog, search, migration, seed</li>
      <li><code>engines/</code>: Vina CLI adapter</li>
      <li><code>worker.py</code>: spawn child entry point</li>
      <li><code>box.py</code> / <code>docking.py</code>: box and docking domain logic</li>
      <li><code>workspace.py</code> / <code>paths.py</code> / <code>results_db.py</code>: workspace, paths, result index</li>
    </ul>
  </details></li>
  <li><code>schemas/</code>: Pydantic request/response contracts</li>
  <li><code>resources/</code>: bundled 1IEP sample and validation resources</li>
</ul>
</details>

<details open>
<summary><strong>web/</strong> · Vue 3 SPA</summary>
<ul>
  <li><code>src/views/</code>: workbench, catalog, box, docking, results</li>
  <li><code>src/stores/</code>: Pinia state</li>
  <li><code>src/components/</code>: panels, 3D viewport, dialogs, sketcher</li>
  <li><code>src/api/</code>: HTTP, WebSocket, QWebChannel</li>
  <li><code>src/types/api.ts</code>: TypeScript mirror of the backend contract</li>
</ul>
</details>

<details open>
<summary><strong>Repository-level directories</strong></summary>
<ul>
  <li><code>docs/</code>: architecture, user guide, validation, structure map</li>
  <li><code>validation/</code>: reproducible validation and benchmark records</li>
  <li><code>scripts/</code>: build, dev, fetching and validation tools</li>
  <li><code>sample/</code>: extra samples; raw data fetched on demand</li>
</ul>
</details>

| Want to change | Open first |
|---|---|
| Desktop window, native menus, file dialogs | `vinastudio/desktop/` |
| API routes, request/response models | `vinastudio/server/routers/`, `vinastudio/schemas/` |
| Job submission, cancellation, event fan-out | `vinastudio/server/job_manager.py`, `ws.py` |
| Docking, box, preparation, analysis | `vinastudio/core/` |
| Child-process entry point, stdout parsing | `vinastudio/core/worker.py` |
| Pages, interaction, state | `web/src/views/`, `stores/`, `components/` |
| Frontend API types | `web/src/types/api.ts` |

## Catalog relationships

| Relationship | Meaning |
|---|---|
| `molecules → molecule_files` | One molecule has several source/prepared files; a file is not the identity |
| `molecules → aliases / tags / sources` | Names, tags and provenance are molecule metadata |
| `studies → study_members → molecules` | Members carry `role` (receptor/ligand/cofactor) and `is_primary` |
| `collections → collection_members → molecules` | Collections are a nested organisation tree, not a Study replacement |
| `libraries → library_members → molecules` | Libraries reference Catalog molecules; members carry `entry_index` |

A molecule's identity is `identity_key`; the same molecule can appear in several Studies, collections and libraries. The database lives at `<workspace>/catalog.sqlite`; structure files remain on the workspace disk.

## Related documents

- [Interactive field guide](https://hubehero.github.io/VinaStudio/experience/)
- [Architecture and the three constraints](ARCHITECTURE.md)
- [Molecule Catalog design](MOLECULE_CATALOG.md)
- [User guide](USER_GUIDE.md)
- [Documentation index](README.md)
