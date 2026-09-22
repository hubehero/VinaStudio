<script setup lang="ts">
import { Aim, Download, RefreshLeft } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { saveImage } from '@/api/bridge'
import {
  DEFAULT_VIEWER_STYLE,
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
const { viewer, ready, error } = useMoleculeViewer(container, { autoReferenceFrame: false })
const loadError = ref<string | null>(null)
const hasMolecule = ref(false)
const dragging = ref(false)

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

watch(ready, (isReady) => { if (isReady) applyAutoRotate() })
watch(() => settings.viewer.autoRotate, applyAutoRotate)
watch(() => settings.viewer.autoRotateSpeed, () => {
  if (settings.viewer.autoRotate) applyAutoRotate()
})

async function applyReceptor(url: string | null): Promise<void> {
  const instance = viewer.value
  if (!instance) {
    return
  }
  try {
    instance.removeReceptor()
    if (url) {
      await instance.loadReceptor(url)
    }
    loadError.value = null
  } catch (cause) {
    loadError.value = cause instanceof Error ? cause.message : String(cause)
  } finally {
    hasMolecule.value = instance.hasMolecule
    if (url) {
      instance.focus()
    } else {
      instance.drawReferenceFrame()
    }
  }
}

async function applyLigand(url: string | null): Promise<void> {
  const instance = viewer.value
  if (!instance) {
    return
  }
  try {
    instance.removeLigand()
    if (url) {
      await instance.loadLigand(url)
    }
    loadError.value = null
  } catch (cause) {
    loadError.value = cause instanceof Error ? cause.message : String(cause)
  } finally {
    hasMolecule.value = instance.hasMolecule
    if (url) {
      instance.focus()
    }
  }
}

// Loading is deferred until the viewer exists; `ready` flips once it does, and
// then the first load runs with whatever URLs are already set.
watch([ready, () => props.receptorUrl], () => void applyReceptor(props.receptorUrl), {
  immediate: true,
})
watch([ready, () => props.ligandUrl], () => void applyLigand(props.ligandUrl), { immediate: true })

/**
 * Load a docked pose from inline SDF content.
 *
 * The pose occupies the ligand slot, so the two ligand sources must never both
 * draw: a view passes either `ligandUrl` or `poseSdfContent`, picked by a
 * computed. Clearing on a null pose is therefore conditional — when a ligand
 * URL stands by, `applyLigand` (created earlier, so it runs first) is mid-swap
 * and an unconditional `removeLigand` here would wipe the ligand it just drew.
 */
async function applyPose(sdfContent: string | null): Promise<void> {
  const instance = viewer.value
  if (!instance || !ready.value) {
    return
  }
  try {
    if (sdfContent) {
      instance.removeLigand()
      instance.loadPoseFromSdf(sdfContent)
    } else if (!props.ligandUrl) {
      instance.removeLigand()
    }
    loadError.value = null
  } catch (cause) {
    loadError.value = cause instanceof Error ? cause.message : String(cause)
  } finally {
    hasMolecule.value = instance.hasMolecule
    if (sdfContent) {
      instance.focus()
    }
  }
}

// Immediate so revisiting this page with a pose already selected still draws it.
watch([ready, () => props.poseSdfContent], () => void applyPose(props.poseSdfContent), {
  immediate: true,
})

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
}, { deep: true })

watch([ready, () => props.orthographic], () => {
  viewer.value?.setProjection(props.orthographic)
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
  instance.raw.zoom(scale)
  instance.raw.render()
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
  instance.raw.render()
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

/* Ensure the WebGL canvas renders crisply and fills its container. */
.viewport__canvas :deep(canvas) {
  display: block;
  width: 100% !important;
  height: 100% !important;
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

.viewport__empty-card {
  max-width: 420px;
  padding: 16px 18px;
  border-radius: var(--vs-radius);
  background: color-mix(in srgb, var(--vs-bg-surface) 88%, transparent);
  border: 1px solid var(--vs-border);
  backdrop-filter: blur(6px);
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
  background: color-mix(in srgb, var(--vs-bg-surface) 86%, transparent);
  border: 1px solid var(--vs-border);
  backdrop-filter: blur(6px);
}
</style>
