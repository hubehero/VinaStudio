import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

import type { RenderQuality, SurfaceKind } from '@/composables/use3Dmol'

/**
 * Viewer preferences — camera behaviour, axes, surface rendering, and quality.
 *
 * Surface visibility and opacity live here as the single source of truth.
 * Both the settings dialog and the style panel bind the same fields, so the
 * two controls always agree and the surface responds immediately.
 *
 * Render quality controls the visual fidelity vs performance trade-off.
 * This only affects rendering, not docking calculations.
 *
 * Theme and language deliberately do *not* live here: the interface store owns
 * them, and keeping a second copy meant a change made in one place was invisible
 * to the other.
 */

const STORAGE_KEY = 'vinastudio-settings'

export interface ViewerSettings {
  invertZoom: boolean
  showAxes: boolean
  axesSize: number
  autoRotate: boolean
  autoRotateSpeed: number
  /** ``null`` means hidden; a ``SurfaceKind`` means visible and sets the type. */
  surfaceKind: SurfaceKind | null
  surfaceOpacity: number
  /** Rendering quality preset: 'low' | 'medium' | 'high'. */
  renderQuality: RenderQuality
}

interface StoredSettings {
  viewer?: Partial<ViewerSettings>
}

const DEFAULT_VIEWER: ViewerSettings = {
  invertZoom: true,
  showAxes: false,
  axesSize: 1.5,
  autoRotate: false,
  autoRotateSpeed: 1.0,
  surfaceKind: null,
  surfaceOpacity: 0.75,
  renderQuality: 'medium',
}

function loadFromStorage(): ViewerSettings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      const parsed = JSON.parse(raw) as StoredSettings
      const stored = parsed.viewer ?? {}
      // Migrate the old boolean ``showSurface`` field that no longer exists.
      const kind: SurfaceKind | null =
        'surfaceKind' in stored
          ? (stored.surfaceKind as SurfaceKind | null)
          : (stored as Record<string, unknown>).showSurface === true
            ? 'SES'
            : null
      const defaults = { ...DEFAULT_VIEWER }
      const migrated: ViewerSettings = {
        ...defaults,
        ...stored,
        surfaceKind: kind,
        surfaceOpacity:
          typeof stored.surfaceOpacity === 'number'
            ? stored.surfaceOpacity
            : defaults.surfaceOpacity,
        renderQuality:
          stored.renderQuality === 'low' || stored.renderQuality === 'high'
            ? stored.renderQuality
            : defaults.renderQuality,
      }
      return migrated
    }
  } catch {
    // Ignore storage failures; fall back to the defaults.
  }
  return { ...DEFAULT_VIEWER }
}

function saveToStorage(viewer: ViewerSettings): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ viewer }))
  } catch {
    // Best-effort only.
  }
}

export const useSettingsStore = defineStore('settings', () => {
  const viewer = ref<ViewerSettings>(loadFromStorage())

  // Persist on change
  watch(viewer, () => {
    saveToStorage(viewer.value)
  }, { deep: true })

  function resetViewer(): void {
    viewer.value = { ...DEFAULT_VIEWER }
  }

  return {
    viewer,
    resetViewer,
  }
})
