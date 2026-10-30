# Reproduced defects — 2026-10-30

Three user-visible defects were reproduced while walking the production build
with real 1IEP data. They are recorded here so the fixes can be reviewed and
regressed; screenshots are in `ui/`.

## D01 — historical report leaked into Workbench as a current result

**Observed**

1. Complete a 1IEP job, producing `-13.25 kcal/mol` / 3 poses.
2. Reset the docking view and change the receptor to `3htb_receptor.pdb`.
3. Open `/report`; it auto-loads the newest completed single job and stores it
   in the shared docking store.
4. Return to `/workbench`: steps **4 运行对接** and **5 结果分析** showed
   `-13.25` and 3 poses even though the current pipeline was `3htb + 1iep`.

**Why it matters:** a historical inspection result looked like the current
pipeline's result. That is a misleading scientific state, not a cosmetic bug.

**Root cause:** `jobResult` had no provenance; Workbench treated any loaded
result as current. Report/History inspection and the live run shared the same
store.

**Fix (working tree)**

- `web/src/stores/docking.ts`: add `isHistoryView`; set false for
  `startDocking`/`startEnsemble`/`reset`, true in `openHistoryJob`.
- `web/src/views/WorkbenchView.vue`: `hasCurrentResult` requires
  `!isHistoryView` and matching receptor/ligand params; the viewport and steps
  use only that value.
- `web/src/views/DockView.vue`: history inspection remains inspectable; a
  pipeline change still clears it.

**Regression check:** `ui/workbench.png` after fix shows steps 4/5 as
`未完成` for the 3htb current pipeline; the historical job remains available in
Report/Dock.

## D02 — historical interaction analysis used the current pipeline receptor

**Observed**

1. Open the 1IEP historical job from Report while the current pipeline is
   `3htb_receptor.pdb`.
2. Run `Analyze Interactions`.
3. The API returned zero contacts, because it combined the 1IEP pose with the
   3htb receptor.

**Why it matters:** a zero-contact answer looked like a property of the pose,
while the input was a different protein. It would silently produce a wrong
scientific interpretation.

**Fix (working tree):** `web/src/components/docking/DockingInteractions.vue`
uses the receptor recorded in `docking.jobResult.params.receptor_path` first;
the current pipeline is only a fallback.

**Regression evidence:** `ui/flow-history-interactions.png` shows 57 contacts
for the 1IEP historical job while the current pipeline names 3htb.

## D03 — Catalog detail pane disappeared below 900 px

**Observed:** at a 900×700 viewport, selecting a Catalog molecule left no detail
pane: the user could not see the 3D preview, prepare action, aliases, tags or
file list. The table remained, but selection became a dead end.

**Before:** `ui/defect-catalog-narrow-hidden.png`.  
**After:** `ui/flow-catalog-narrow-detail.png` (detail is a bottom full-width
row; the table remains scrollable).

**Fix (working tree):** `MoleculeCatalogView.vue` keeps `.catalog-detail` as a
second grid row at ≤900 px instead of `display:none`, with a bounded height and
internal scroll.

## Not defects

- Software-renderer banner in screenshots: the test container exposes SwiftShader
  without GPU; the banner is the expected diagnostic. It is not counted as a UI
  pass or failure.
- The 1IEP job produced 3 poses, not the requested 20: Vina's energy window and
  minimum-RMSD filter can return fewer. The result table and CSV report the
  actual count.

## D04 — software-render desktop start left WebGL unusable

**Observed:** launching the desktop app with `VINASTUDIO_SOFTWARE_RENDER=1`
started the API and WebSocket, but the embedded interface logged:

```
js: TypeError: Cannot read properties of null (reading 'getParameter')
js: [vinastudio] failed to create the 3Dmol viewer ...
```

The API was healthy; only the 3D viewport failed. The previous software escape
hatch used `--disable-gpu` without a WebGL replacement context.

**Why it matters:** the explicit software-rendering path is what users on broken
drivers are told to use; starting it with a dead viewport defeats the fallback.

**Fix (working tree):** `vinastudio/desktop/env.py` asks ANGLE for SwiftShader
(`--enable-unsafe-swiftshader --use-gl=angle --use-angle=swiftshader`) instead
of disabling the GL context. Unit expectations updated in
`tests/unit/test_desktop_env.py`.

**Regression evidence:** `completion/raw/desktop-startup-angle.log` starts the
desktop app with no 3Dmol/WebGL error. `completion/raw/desktop-startup.log`
retains the pre-fix failure. This is a startup smoke; native dialogs and
QWebChannel interactions still require a human desktop session.

## D05 — cancelled screening history rendered a 1500% progress

**Observed:** the screening history contained an old cancelled run whose stored
`progress` was `1500`. The table rendered `1500%` and the progress bar received
an out-of-range value; the current full run itself was correct.

**Why it matters:** a progress number outside 0–100 is visibly impossible and
makes a cancelled historical row look like a live/model state.

**Fix (working tree):** `ScreeningView.vue` clamps both the active status bar
and historical table rows to 0–100 with `progressPercent()`; the stored backend
value is left untouched so the historical record is not rewritten.

**Before/after:** `completion/ui/screening-progress-clamped.png` after reload
shows 100%; the pre-fix state is retained in
`completion/ui/defect-screening-1500.png`. The full run shows `123/125 completed,
2 failed, best −12.98`.

## D06 — odd-voxel affinity-map request returned HTTP 500

**Observed:** `POST /api/box/write-maps` with the 1IEP auto-box
`(16.664, 24.739, 21.526)` and default `forceEvenVoxels=false` reached Vina and
returned a bare `RuntimeError: ... Number of voxels ... is odd`, surfaced as
**500**. The UI already exposes `canWriteMaps` for this exact condition, but an
API caller got an internal error instead of the remedy.

**Fix (working tree):** `server/routers/box.py` builds the same `Box` model as
the UI before invoking Vina and returns a 422:
`cannot write affinity maps with odd voxel counts; enable forceEvenVoxels and retry`.
With `forceEvenVoxels=true`, 22 map files were written successfully.

**Evidence:** `completion/raw/write-maps-odd-response.txt` and
`completion/raw/write-maps-even.json`; regression test
`tests/integration/test_box_api.py::test_write_maps_rejects_odd_voxels_before_vina`.
