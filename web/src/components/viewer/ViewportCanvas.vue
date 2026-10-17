<script setup lang="ts">
import { Aim, Close, Download, RefreshLeft, WarningFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { saveImage } from '@/api/bridge'
import {
  DEFAULT_VIEWER_STYLE,
  rendererInfo,
  useMoleculeViewer,
  type BoxGeometry,
  type InteractionData,
  type ViewerStyle,
} from '@/composables/use3Dmol'
import { useSettingsStore } from '@/stores/settings'
import { useUiStore } from '@/stores/ui'

/**
 * The 3D stage.
 *
 * Molecules arrive as URLs rather than objects, because the backend writes
 * every prepared file into its workspace and serves it from `/artifacts`. That
 * keeps large structures out of the JSON API and lets the fetch be cached.
 *
 * The URLs must point at *renderable* formats — PDB for receptors and SDF for
 * ligands. 3Dmol cannot read PDBQT, which is why the backend writes both.
 *
 * For docked poses, poseSdfContent provides the inline SDF string directly
 * (extracted from the multi-molecule posesSdf result). It shares the ligand
 * slot with ligandUrl: pass one or the other, never both at once.
 *
 * Interactions are protein-ligand interaction data for 3D visualization
 * (hydrogen bonds, hydrophobic contacts, etc.).
 */
const props = withDefaults(
  defineProps<{
    receptorUrl?: string | null
    ligandUrl?: string | null
    poseSdfContent?: string | null
    interactions?: InteractionData[]
    box?: BoxGeometry | null
    style?: ViewerStyle
    orthographic?: boolean
    /** Whether holding shift and dragging may move the box. */
    boxDraggable?: boolean
  }>(),
  {
    receptorUrl: null,
    ligandUrl: null,
    poseSdfContent: null,
    interactions: () => [],
    box: null,
    style: undefined,
    orthographic: false,
    boxDraggable: false,
  },
)

const emit = defineEmits<{ 'box-moved': [center: [number, number, number]] }>()

const ui = useUiStore()
const settings = useSettingsStore()
const { t } = useI18n()

const container = ref<HTMLElement | null>(null)
const { viewer, ready, error, recreate } = useMoleculeViewer(container, {
  autoReferenceFrame: false,
  // Getters so a rebuild always binds the latest preset and switch states.
  quality: () => settings.viewer.renderQuality,
  antialiasOff: () => settings.viewer.antialiasOff ?? false,
  adaptiveAO: () => settings.viewer.adaptiveAO ?? false,
})
const loadError = ref<string | null>(null)
const hasMolecule = ref(false)
const dragging = ref(false)
/** Session-level dismissal of the software-renderer warning pill. */
const rendererWarnDismissed = ref(false)

/**
 * Surface kind and opacity live in ``settings.viewer`` as the single source of
 * truth.  The live ``props.style`` may also carry surface fields (from the box
 * store), but settings override them so the settings dialog and style panel
 * always agree.  The rest of the style (receptor, ligand) comes from
 * ``props.style`` or falls back to the default.
 */
const effectiveStyle = computed<ViewerStyle>(() => {
  const base = props.style ?? DEFAULT_VIEWER_STYLE
  return {
    ...base,
    surface: settings.viewer.surfaceKind,
    surfaceOpacity: settings.viewer.surfaceOpacity,
  }
})

/** Stage colours: the 3D scene must contrast with the surrounding chrome. */
const STAGE_BACKGROUND: Record<'dark' | 'light', string> = {
  dark: '#0d1526',
  light: '#f4f6fb',
}

watch(
  () => ui.resolvedTheme,
  (theme) => viewer.value?.setBackground(STAGE_BACKGROUND[theme]),
)

// ---------------------------------------------------------------------------
// Auto-rotation — driven entirely by the settings store so the slider in the
// settings dialog takes effect immediately on every viewport.
// ---------------------------------------------------------------------------

function applyAutoRotate(): void {
  const instance = viewer.value
  if (!instance) return
  if (settings.viewer.autoRotate) {
    instance.raw.spin('y', settings.viewer.autoRotateSpeed)
  } else {
    instance.raw.spin(false)
  }
}

watch(ready, (isReady) => {
  if (!isReady) return
  // A rebuilt viewer starts on the constructor's default background; re-assert
  // the theme colour so light mode never flashes the dark default.
  viewer.value?.setBackground(STAGE_BACKGROUND[ui.resolvedTheme])
  applyAutoRotate()
})
watch(() => settings.viewer.autoRotate, applyAutoRotate)
watch(() => settings.viewer.autoRotateSpeed, () => {
  if (settings.viewer.autoRotate) applyAutoRotate()
})

// ---------------------------------------------------------------------------
// Molecule loading — single coordinated loader
//
// All molecule state (receptor, ligand, pose) is applied together to avoid
// race conditions between concurrent async watchers.  A generation counter
// discards the result of any stale operation so only the latest prop values
// take effect, even when requests resolve out of order.
// ---------------------------------------------------------------------------
let loadGeneration = 0

/**
 * Apply all molecule props in one atomic operation.
 *
 * The receptor is loaded first; removeReceptor() internally removes the
 * ligand too, so the ligand is always loaded /after/ the receptor.  Pose
 * SDF content shares the ligand slot with ligandUrl — pose takes priority
 * when both are set.
 *
 * The receptor is only rebuilt when its URL changes: pose navigation fires
 * this watcher on every step and re-fetching + re-styling the whole receptor
 * each time was the dominant cost of browsing poses. The residual risk — the
 * same URL rewritten in place while this view stays mounted — does not occur:
 * receptor preparation happens on /molecules, where this view is unmounted
 * (the module-level text cache in use3Dmol rests on the same conclusion).
 */
let loadedReceptorUrl: string | null = null
/** The ligandUrl this viewer last applied — the other half of molecule
 * identity; a poseSdfContent-only swap never counts as a new molecule. */
let loadedLigandUrl: string | null = null

async function applyMolecules(): Promise<void> {
  const instance = viewer.value
  if (!instance || !ready.value) return

  const gen = ++loadGeneration
  // Camera refit and the highlight repaint belong to molecule identity
  // changes (new receptor/ligand, receptor rebuild, viewer recreate) —
  // never to a pose step, which only swaps content inside the existing
  // ligand slot.
  const moleculeIdentityChanged =
    props.receptorUrl !== loadedReceptorUrl || props.ligandUrl !== loadedLigandUrl

  try {
    // --- receptor ---
    if (props.receptorUrl !== loadedReceptorUrl) {
      instance.removeReceptor()          // also removes ligand + surface
      if (props.receptorUrl) {
        await instance.loadReceptor(props.receptorUrl)
      }
      if (gen !== loadGeneration) return  // stale — a newer call superseded us
      loadedReceptorUrl = props.receptorUrl
    } else {
      // Receptor unchanged: keep it (and its surface), swap only the ligand.
      instance.removeLigand()
      if (gen !== loadGeneration) return
    }

    // --- ligand / pose ---
    if (props.poseSdfContent) {
      instance.loadPoseFromSdf(props.poseSdfContent)
    } else if (props.ligandUrl) {
      await instance.loadLigand(props.ligandUrl)
    }
    if (gen !== loadGeneration) return
    loadedLigandUrl = props.ligandUrl

    loadError.value = null
  } catch (cause) {
    if (gen !== loadGeneration) return
    loadError.value = cause instanceof Error ? cause.message : String(cause)
  } finally {
    if (gen !== loadGeneration) return
    hasMolecule.value = instance.hasMolecule
    if (instance.hasMolecule) {
      // Pose stepping keeps the user's camera — a refocus would yank a
      // rotated view back to fit — and skips the highlight repaint: the
      // ligand-slot swap never breaks the receptor styles.  Receptor model
      // rebuilds still re-apply residue highlights the async load would
      // otherwise wipe (TASK-12 §6).
      if (moleculeIdentityChanged) {
        instance.focus()
        scheduleHighlight()
      }
    } else {
      instance.drawReferenceFrame()
      scheduleHighlight()
    }
  }
}

// Trigger on any molecule-prop change or viewer becoming ready.
watch(
  [ready, () => props.receptorUrl, () => props.ligandUrl, () => props.poseSdfContent],
  () => void applyMolecules(),
  { immediate: true },
)

// Draw interactions when the array changes.
watch([ready, () => props.interactions], () => {
  const instance = viewer.value
  if (!instance || !ready.value) {
    return
  }
  if (props.interactions.length > 0) {
    instance.drawInteractions(props.interactions)
  } else {
    instance.removeInteractions()
  }
})

// The box only exists once a molecule is on screen; before that the reference
// frame stands in for it.
watch([ready, () => props.box], () => {
  const instance = viewer.value
  if (!instance || !ready.value) {
    return
  }
  if (props.box && props.receptorUrl) {
    instance.setBox(props.box)
  } else {
    instance.setBox(null)
    instance.drawReferenceFrame()
  }
})

watch([ready, () => effectiveStyle.value], () => {
  if (viewer.value) {
    void viewer.value.applyStyle(effectiveStyle.value)
  }
})

watch([ready, () => props.orthographic], () => {
  viewer.value?.setProjection(props.orthographic)
})

// Quality presets bind antialias/cartoonQuality at construction time, so a
// preset change must rebuild the viewer to take full effect — a runtime
// AO-only tweak cannot retarget those bindings. While not ready the quality
// getter already supplies the new preset to the pending construction.
// antialiasOff joins the same channel: it also binds at construction.
watch(() => [settings.viewer.renderQuality, settings.viewer.antialiasOff], () => {
  if (ready.value) {
    // The rebuild starts from an empty container — forget which molecules
    // the cache believes are loaded, or applyMolecules would skip re-adding
    // them.
    loadedReceptorUrl = null
    loadedLigandUrl = null
    recreate()
  }
})

// Adaptive AO is runtime-adjustable — toggle the kernel in place, no recreate.
watch(() => settings.viewer.adaptiveAO, (on) => {
  viewer.value?.setAdaptiveAO(on ?? false)
})

// ---------------------------------------------------------------------------
// box dragging
// ---------------------------------------------------------------------------

let dragOrigin: { x: number; y: number; center: [number, number, number] } | null = null

/**
 * Shift-drag moves the box; a plain drag still rotates the view.
 *
 * 3Dmol's own mouse handlers are bound to the canvas, so a capture-phase
 * listener on the container stops the event before it reaches them. Without
 * that, the view would rotate at the same time as the box moved.
 */
function onPointerDown(event: PointerEvent): void {
  if (!props.boxDraggable || !props.box || !event.shiftKey) {
    return
  }
  event.preventDefault()
  event.stopPropagation()
  dragOrigin = {
    x: event.clientX,
    y: event.clientY,
    center: [...props.box.center] as [number, number, number],
  }
  dragging.value = true
  window.addEventListener('pointermove', onPointerMove, true)
  window.addEventListener('pointerup', onPointerUp, true)
}

function onPointerMove(event: PointerEvent): void {
  const origin = dragOrigin
  const instance = viewer.value
  if (!origin || !instance) {
    return
  }
  event.preventDefault()
  event.stopPropagation()

  // Convert the screen displacement into a model-space one at the depth of the
  // box centre, so the box tracks the pointer rather than the camera.
  const delta = instance.raw.screenOffsetToModel(
    event.clientX - origin.x,
    event.clientY - origin.y,
    origin.center[2],
  )
  emit('box-moved', [
    Math.round((origin.center[0] + delta.x) * 1000) / 1000,
    Math.round((origin.center[1] + delta.y) * 1000) / 1000,
    Math.round((origin.center[2] + delta.z) * 1000) / 1000,
  ])
}

function onPointerUp(event: PointerEvent): void {
  event.stopPropagation()
  dragOrigin = null
  dragging.value = false
  window.removeEventListener('pointermove', onPointerMove, true)
  window.removeEventListener('pointerup', onPointerUp, true)
}

onBeforeUnmount(() => {
  window.removeEventListener('pointermove', onPointerMove, true)
  window.removeEventListener('pointerup', onPointerUp, true)
  removeWheelHandler()
  if (highlightFrame !== null) {
    cancelAnimationFrame(highlightFrame)
    highlightFrame = null
  }
})

// ---------------------------------------------------------------------------
// Scroll wheel zoom with optional inversion
// ---------------------------------------------------------------------------

let wheelTarget: HTMLElement | null = null

function removeWheelHandler(): void {
  if (wheelTarget) {
    wheelTarget.removeEventListener('wheel', onWheel, { capture: true })
    wheelTarget = null
  }
}

function onWheel(event: WheelEvent): void {
  const instance = viewer.value
  if (!instance || !ready.value) {
    return
  }

  event.preventDefault()
  event.stopPropagation()

  // deltaY > 0 = scroll down, deltaY < 0 = scroll up
  // With invertZoom=true: scroll down = zoom in, scroll up = zoom out
  // With invertZoom=false: scroll down = zoom out, scroll up = zoom in (default)
  const scrollDown = event.deltaY > 0
  const invert = settings.viewer.invertZoom
  const zoomIn = invert ? scrollDown : !scrollDown
  const scale = zoomIn ? 0.85 : 1.15
  // Coalesced: a wheel burst fires many events per frame, and each direct
  // render would spend a full ambient-occlusion pass on frames nobody sees.
  instance.zoomBy(scale)
}

watch(ready, (isReady) => {
  removeWheelHandler()
  if (isReady && container.value) {
    const canvas = container.value.querySelector('canvas') as HTMLElement | null
    wheelTarget = canvas ?? container.value
    wheelTarget.addEventListener('wheel', onWheel, { capture: true, passive: false })
  }
})

// ---------------------------------------------------------------------------
// Coordinate axes
// ---------------------------------------------------------------------------

// The three cylinders currently drawn, so they can actually be removed again.
let axesShapes: unknown[] = []

function updateAxes(): void {
  const instance = viewer.value
  if (!instance || !ready.value) {
    return
  }

  // Remove existing axes
  for (const shape of axesShapes) {
    instance.raw.removeShape(shape as never)
  }
  axesShapes = []

  if (settings.viewer.showAxes) {
    const s = settings.viewer.axesSize
    // X axis (red)
    axesShapes.push(instance.raw.addCylinder({
      start: { x: 0, y: 0, z: 0 },
      end: { x: s, y: 0, z: 0 },
      color: '#ef4444',
      radius: 0.05,
      fromCap: 1,
      toCap: 2,
    }))
    // Y axis (green)
    axesShapes.push(instance.raw.addCylinder({
      start: { x: 0, y: 0, z: 0 },
      end: { x: 0, y: s, z: 0 },
      color: '#22c55e',
      radius: 0.05,
      fromCap: 1,
      toCap: 2,
    }))
    // Z axis (blue)
    axesShapes.push(instance.raw.addCylinder({
      start: { x: 0, y: 0, z: 0 },
      end: { x: 0, y: 0, z: s },
      color: '#3b82f6',
      radius: 0.05,
      fromCap: 1,
      toCap: 2,
    }))
  }
  instance.scheduleRender()
}

watch(ready, (isReady) => {
  if (isReady) {
    updateAxes()
  }
})

watch(() => settings.viewer.showAxes, () => {
  if (ready.value) {
    updateAxes()
  }
})

watch(() => settings.viewer.axesSize, () => {
  if (ready.value && settings.viewer.showAxes) {
    updateAxes()
  }
})

function resetView(): void {
  const instance = viewer.value
  if (!instance) {
    return
  }
  if (instance.hasMolecule) {
    instance.focus()
  } else {
    instance.drawReferenceFrame()
  }
  updateAxes()
}

async function exportPng(): Promise<void> {
  const instance = viewer.value
  if (!instance) {
    return
  }
  try {
    if (await saveImage(instance.pngDataUrl(), 'vinastudio-view.png')) {
      ElMessage.success(t('common.success'))
    }
  } catch {
    ElMessage.error(t('common.error'))
  }
}

const emptyTitle = computed(() => t('workbench.viewport.emptyTitle'))
const emptyBody = computed(() => t('workbench.viewport.emptyBody'))

// ---------------------------------------------------------------------------
// residue highlighting (TASK-12 §6)
// ---------------------------------------------------------------------------

/** Keys re-applied after every molecule reload; null means the sequence view
 * never asked, so ordinary canvases keep their own style path untouched. */
let highlightKeys: string[] | null = null

/** Mirror of MoleculeViewer's receptor base: a highlight reset must repaint
 * exactly what the style system would. setStyle replaces atom styles but
 * leaves shapes (box, axes, interaction annotations) alone — which is why
 * clearing goes through here and never through removeAllStyles/removeAllShapes. */
function receptorBaseStyle(style: ViewerStyle): Record<string, unknown> {
  const colour =
    style.receptorColour === 'spectrum'
      ? { color: 'spectrum' }
      : style.receptorColour === 'ss'
        ? { colorscheme: 'ssPyMol' }
        : style.receptorColour === 'element'
          ? { colorscheme: 'default' }
          : { colorscheme: 'chain' }
  switch (style.receptor) {
    case 'cartoon':
      return { cartoon: { ...colour, tubes: false, opacity: 1.0 } }
    case 'stick':
      return { stick: { ...colour, radius: 0.12 } }
    case 'sphere':
      return { sphere: { ...colour, scale: 0.22 } }
    case 'line':
      return { line: { ...colour, linewidth: 1.5 } }
    default:
      return { [style.receptor]: colour }
  }
}

function applyHighlight(): void {
  const instance = viewer.value
  if (!instance || !ready.value || highlightKeys === null) return
  instance.raw.setStyle({}, receptorBaseStyle(effectiveStyle.value))
  for (const key of highlightKeys) {
    const sep = key.indexOf(':')
    if (sep <= 0) continue
    instance.raw.addStyle(
      { chain: key.slice(0, sep), resi: Number(key.slice(sep + 1)) },
      { stick: { colorscheme: 'greenCarbon', radius: 0.15 } },
    )
  }
  instance.scheduleRender()
}

/**
 * Coalesce highlight repaints to at most one per frame.  A fast sweep across
 * sequence cells fires one event per cell; each one would otherwise redo a
 * full receptor restyle.  ``applyHighlight`` itself is unchanged — this only
 * batches when it runs; unmount cancels the pending frame (same convention as
 * ``_cancelSurfaceTimer`` in use3Dmol).
 */
let highlightFrame: number | null = null
function scheduleHighlight(): void {
  if (highlightFrame !== null) return
  highlightFrame = requestAnimationFrame(() => {
    highlightFrame = null
    applyHighlight()
  })
}

/**
 * Highlight receptor residues as green sticks (TASK-12 §6). ``null`` turns
 * the feature off without touching styles — the next load paints its own
 * base; an empty array clears by resetting the receptor base.
 */
function highlightResidues(keys: string[] | null): void {
  if (keys === null) {
    highlightKeys = null
    return
  }
  highlightKeys = keys
  scheduleHighlight()
}

defineExpose({ highlightResidues })
</script>

<template>
  <div class="viewport">
    <div
      ref="container"
      class="viewport__canvas"
      :class="{ 'is-dragging': dragging }"
      @pointerdown.capture="onPointerDown"
    />

    <div v-if="!ready && !error" class="viewport__overlay viewport__overlay--center">
      <el-icon class="is-loading"><RefreshLeft /></el-icon>
      <span>{{ t('common.loading') }}</span>
    </div>

    <div v-if="error || loadError" class="viewport__overlay viewport__overlay--center is-error">
      <span>{{ error ?? loadError }}</span>
    </div>

    <div v-if="ready && !hasMolecule" class="viewport__overlay viewport__empty">
      <div class="viewport__empty-card">
        <span class="viewport__badge">{{ t('workbench.viewport.demoBadge') }}</span>
        <h3>{{ emptyTitle }}</h3>
        <p>{{ emptyBody }}</p>
      </div>
    </div>

    <div v-if="boxDraggable && hasMolecule" class="viewport__hint">
      {{ t('box.dragHint') }}
    </div>

    <!-- Bottom-right: the one free corner (toolbar top-right, hint top-left,
         empty card bottom-left). Shown only when Chromium silently fell back
         to a CPU rasteriser. -->
    <div
      v-if="rendererInfo?.software && !rendererWarnDismissed"
      class="viewport__sw-warn"
      role="status"
    >
      <el-icon :size="14" class="viewport__sw-warn__icon"><WarningFilled /></el-icon>
      <div class="viewport__sw-warn__text">
        <strong>{{ t('viewport.softwareRenderer') }}</strong>
        <span>{{ t('viewport.softwareRendererHint', { renderer: rendererInfo.renderer }) }}</span>
      </div>
      <el-button
        size="small"
        text
        :aria-label="t('common.close')"
        @click="rendererWarnDismissed = true"
      >
        <el-icon><Close /></el-icon>
      </el-button>
    </div>

    <div class="viewport__toolbar">
      <el-tooltip :content="t('viewport.focusView')" placement="bottom">
        <el-button size="small" text :disabled="!ready" @click="resetView">
          <el-icon><Aim /></el-icon>
        </el-button>
      </el-tooltip>
      <el-tooltip :content="t('viewport.exportPng')" placement="bottom">
        <el-button size="small" text :disabled="!ready" @click="exportPng">
          <el-icon><Download /></el-icon>
        </el-button>
      </el-tooltip>
    </div>
  </div>
</template>

<style scoped>
.viewport {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 320px;
  border: 1px solid var(--vs-border);
  border-radius: var(--vs-radius-lg);
  overflow: hidden;
  background: var(--vs-bg-sunken);
}

.viewport__canvas {
  width: 100%;
  height: 100%;
}

/*
 * Ensure the WebGL canvas renders crisply and fills its container.
 *
 * We deliberately avoid `!important` on width/height: 3Dmol manages the
 * canvas dimensions internally via ResizeObserver and sets inline styles
 * for both the buffer resolution and display size.  Forcing `100%` with
 * `!important` overrides those inline styles, which can cause the WebGL
 * framebuffer resolution to diverge from the CSS display size.  When that
 * happens the projection matrix is computed for one resolution while the
 * browser stretches/compresses the content to fit another — producing the
 * deformation and disappearing artefacts visible at certain camera angles.
 *
 * Instead we hint the layout engine to fill the container with flex and
 * let 3Dmol own the actual pixel dimensions.
 */
.viewport__canvas {
  display: flex;
}

.viewport__canvas :deep(canvas) {
  display: block;
  flex: 1;
  min-width: 0;
  min-height: 0;
  outline: none;
}

.viewport__canvas.is-dragging {
  cursor: move;
}

.viewport__overlay {
  position: absolute;
  inset: 0;
  display: flex;
  pointer-events: none;
  padding: 24px;
}

.viewport__overlay--center {
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: var(--vs-text-muted);
  text-align: center;
}

.viewport__overlay--center.is-error {
  color: var(--vs-danger);
}

.viewport__empty {
  align-items: flex-end;
  justify-content: flex-start;
}

/*
 * Cards floating over the stage are opaque, never `backdrop-filter: blur()`.
 *
 * A blurred backdrop has to be read back out of the compositor and re-blurred
 * whenever what is behind it changes — and what is behind it is a WebGL canvas
 * that redraws every frame while the user rotates the view. That readback
 * costs a large slice of the frame budget and makes the canvas flicker, so
 * these overlays paint a solid surface colour instead.
 */
.viewport__empty-card {
  max-width: 420px;
  padding: 16px 18px;
  border-radius: var(--vs-radius);
  background: var(--vs-bg-surface);
  border: 1px solid var(--vs-border);
}

.viewport__badge {
  display: inline-block;
  margin-bottom: 8px;
  padding: 1px 8px;
  border-radius: 999px;
  background: var(--vs-accent-soft);
  color: var(--vs-accent);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.02em;
}

.viewport__empty-card h3 {
  font-size: 14px;
  margin-bottom: 6px;
}

.viewport__empty-card p {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.65;
  color: var(--vs-text-muted);
}

.viewport__hint {
  position: absolute;
  left: 12px;
  top: 12px;
  padding: 3px 9px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--vs-bg-surface) 86%, transparent);
  border: 1px solid var(--vs-border);
  color: var(--vs-text-faint);
  font-size: 11px;
  pointer-events: none;
}

.viewport__toolbar {
  position: absolute;
  top: 10px;
  right: 10px;
  display: flex;
  gap: 2px;
  padding: 3px;
  border-radius: var(--vs-radius);
  /* Opaque, not blurred: see .viewport__empty-card. */
  background: var(--vs-bg-surface);
  border: 1px solid var(--vs-border);
}

.viewport__sw-warn {
  position: absolute;
  right: 10px;
  bottom: 10px;
  display: flex;
  align-items: flex-start;
  gap: 8px;
  max-width: 320px;
  padding: 8px 10px;
  border-radius: var(--vs-radius);
  /* Opaque, not blurred: see .viewport__empty-card. */
  background: var(--vs-bg-surface);
  border: 1px solid color-mix(in srgb, var(--vs-warning) 45%, var(--vs-border));
  color: var(--vs-warning);
  font-size: 11.5px;
  line-height: 1.5;
  z-index: 2;
}

.viewport__sw-warn__icon {
  margin-top: 2px;
  flex: none;
}

.viewport__sw-warn__text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  color: var(--vs-text-muted);
}

.viewport__sw-warn__text strong {
  color: var(--vs-warning);
}
</style>
