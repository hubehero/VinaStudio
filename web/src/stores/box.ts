import { defineStore } from 'pinia'
import { computed, reactive, ref, watch, type Ref } from 'vue'

import { ApiError, api } from '@/api/http'
import { DEFAULT_VIEWER_STYLE, type BoxGeometry, type ViewerStyle } from '@/composables/use3Dmol'
import type { BoxMetrics } from '@/types/api'

/** Defaults mirror the upstream tutorial's 1iep box. */
const DEFAULT_CENTER: [number, number, number] = [15.19, 53.903, 16.917]
const DEFAULT_SIZE: [number, number, number] = [20, 20, 20]

/** How long to wait after the last edit before asking the backend to measure. */
const MEASURE_DEBOUNCE_MS = 180

export const useBoxStore = defineStore('box', () => {
  // `ref` rather than `reactive`: a tuple keeps its fixed length, so indexing it
  // stays `number` instead of widening to `number | undefined`.
  const center = ref<[number, number, number]>([...DEFAULT_CENTER])
  const size = ref<[number, number, number]>([...DEFAULT_SIZE])
  const spacing = ref(0.375)
  const forceEvenVoxels = ref(false)

  /**
   * Derived quantities come from the backend rather than being recomputed here.
   * The voxel and grid-point rules are Vina's, and having one definition in
   * `core/box.py` is what keeps this panel from disagreeing with what
   * `write_maps` will actually accept.
   */
  const metrics = ref<BoxMetrics | null>(null)
  const measuring = ref(false)
  const error = ref<string | null>(null)
  const autoboxPoints = ref<number | null>(null)
  const autoboxSource = ref<string | null>(null)

  const style = reactive<ViewerStyle>({ ...DEFAULT_VIEWER_STYLE })
  const orthographic = ref(false)

  const geometry = computed<BoxGeometry>(() => ({
    center: center.value,
    size: size.value,
  }))

  const voxels = computed(() => metrics.value?.voxels ?? [0, 0, 0])
  /** Total grid cells across the three axes, for the cost hint in the panel. */
  const gridCells = computed(() => voxels.value.reduce((total, count) => total * count, 1))
  const warnings = computed(() => metrics.value?.warnings ?? [])
  const canWriteMaps = computed(() => metrics.value?.canWriteMaps ?? false)

  function payload() {
    return {
      center: center.value,
      size: size.value,
      spacing: spacing.value,
      forceEvenVoxels: forceEvenVoxels.value,
    }
  }

  async function measure(): Promise<void> {
    measuring.value = true
    error.value = null
    try {
      metrics.value = await api.measureBox(payload())
    } catch (cause) {
      metrics.value = null
      error.value = cause instanceof ApiError ? cause.message : String(cause)
    } finally {
      measuring.value = false
    }
  }

  // Editing any field re-measures, debounced so dragging a slider, or the box in
  // the viewport, does not issue a request per pixel.
  let timer: ReturnType<typeof setTimeout> | null = null
  function scheduleMeasure(): void {
    if (timer !== null) {
      clearTimeout(timer)
    }
    timer = setTimeout(() => {
      timer = null
      void measure()
    }, MEASURE_DEBOUNCE_MS)
  }

  watch(
    [center, size, spacing, forceEvenVoxels],
    scheduleMeasure,
    { deep: true },
  )

  /** Index of an axis, kept as a literal union so tuple access stays typed. */
  type Axis = 0 | 1 | 2

  function replaceAxis(
    target: Ref<[number, number, number]>,
    axis: Axis,
    value: number,
    minimum: number,
  ): void {
    const next: [number, number, number] = [...target.value]
    next[axis] = Math.max(round(value), minimum)
    target.value = next
  }

  function setCenter(next: [number, number, number]): void {
    center.value = [round(next[0]), round(next[1]), round(next[2])]
  }

  function setCenterAxis(axis: Axis, value: number): void {
    // The centre may be negative; only the size has a lower bound.
    replaceAxis(center, axis, value, Number.NEGATIVE_INFINITY)
  }

  function setSize(next: [number, number, number]): void {
    size.value = [
      Math.max(round(next[0]), 1),
      Math.max(round(next[1]), 1),
      Math.max(round(next[2]), 1),
    ]
  }

  function setSizeAxis(axis: Axis, value: number): void {
    // A zero or negative edge is not a box; clamping here also keeps the
    // viewport from drawing a degenerate shape while the backend would reject it.
    replaceAxis(size, axis, value, 1)
  }

  async function autoboxFromLigand(path: string, extend: number): Promise<boolean> {
    return runAutobox(() =>
      api.autoboxFromLigand({ path, extend, spacing: spacing.value, forceEvenVoxels: forceEvenVoxels.value }),
    )
  }

  async function autoboxFromResidues(
    path: string,
    residues: string[],
    extend: number,
  ): Promise<boolean> {
    return runAutobox(() =>
      api.autoboxFromResidues({
        path,
        residues,
        extend,
        spacing: spacing.value,
        forceEvenVoxels: forceEvenVoxels.value,
      }),
    )
  }

  async function runAutobox(
    call: () => Promise<{ box: BoxMetrics; points: number; source: string }>,
  ): Promise<boolean> {
    measuring.value = true
    error.value = null
    try {
      const result = await call()
      applyMetrics(result.box)
      autoboxPoints.value = result.points
      autoboxSource.value = result.source
      return true
    } catch (cause) {
      error.value = cause instanceof ApiError ? cause.message : String(cause)
      return false
    } finally {
      measuring.value = false
    }
  }

  /** Adopt a measured box, including any rounding the backend applied. */
  function applyMetrics(next: BoxMetrics): void {
    metrics.value = next
    center.value = [next.center[0], next.center[1], next.center[2]]
    size.value = [next.size[0], next.size[1], next.size[2]]
    spacing.value = next.spacing
    forceEvenVoxels.value = next.forceEvenVoxels
  }

  async function exportConfig(): Promise<string> {
    const result = await api.boxToConfig(payload())
    return result.text
  }

  async function importConfig(text: string): Promise<boolean> {
    measuring.value = true
    error.value = null
    try {
      applyMetrics(await api.boxFromConfig(text))
      return true
    } catch (cause) {
      error.value = cause instanceof ApiError ? cause.message : String(cause)
      return false
    } finally {
      measuring.value = false
    }
  }

  function reset(): void {
    setCenter([...DEFAULT_CENTER])
    setSize([...DEFAULT_SIZE])
    autoboxPoints.value = null
    autoboxSource.value = null
  }

  return {
    center,
    size,
    spacing,
    forceEvenVoxels,
    metrics,
    measuring,
    error,
    geometry,
    voxels,
    gridCells,
    warnings,
    canWriteMaps,
    autoboxPoints,
    autoboxSource,
    style,
    orthographic,
    measure,
    setCenter,
    setCenterAxis,
    setSize,
    setSizeAxis,
    reset,
    autoboxFromLigand,
    autoboxFromResidues,
    exportConfig,
    importConfig,
  }
})

function round(value: number): number {
  return Math.round(value * 1000) / 1000
}
