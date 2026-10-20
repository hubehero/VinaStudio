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
  /**
   * Force construction-time antialiasing off, overriding the preset.
   *
   * On by default (the user's ruling, 2026-10-20): AA on QtWebEngine 6 for
   * Windows flickers unpredictably, and AA is what doubles 3Dmol's draw buffer
   * (2× per axis, 4× the pixels) on the same compositor path. A user who wants
   * antialiased edges can still switch it off.
   */
  antialiasOff: boolean
  /**
   * Frame-time-driven ambient-occlusion downgrade (3Dmol has no geometric
   * LOD; AO is the most expensive runtime-adjustable style pass). On by
   * default: it changes nothing while frames are cheap, and AO is the one pass
   * whose cost the viewport can shed without touching the scene.
   */
  adaptiveAO: boolean
}

export type MoleculeViewMode = 'type' | 'source'

export interface MoleculeSettings {
  /** Molecule manager list organisation: by type, or by provenance group. */
  viewMode: MoleculeViewMode
}

interface StoredSettings {
  viewer?: Partial<ViewerSettings>
  molecules?: Partial<MoleculeSettings>
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
  antialiasOff: true,
  adaptiveAO: true,
}

const DEFAULT_MOLECULES: MoleculeSettings = {
  viewMode: 'type',
}

function loadFromStorage(): { viewer: ViewerSettings; molecules: MoleculeSettings } {
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
        // An absent key means "never chosen", so it follows today's default
        // (AA off); a stored boolean is a user's decision and stays one.
        antialiasOff:
          typeof stored.antialiasOff === 'boolean'
            ? stored.antialiasOff
            : defaults.antialiasOff,
        // Same rule as the key above: an absent value follows today's default,
        // while a stored `false` is a user's decision and stays one.
        adaptiveAO:
          typeof stored.adaptiveAO === 'boolean' ? stored.adaptiveAO : defaults.adaptiveAO,
      }
      return { viewer: migrated, molecules: migrateMolecules(parsed.molecules) }
    }
  } catch {
    // Ignore storage failures; fall back to the defaults.
  }
  return { viewer: { ...DEFAULT_VIEWER }, molecules: { ...DEFAULT_MOLECULES } }
}

/** Anything but a stored 'source' falls back to 'type' (older payloads lack it). */
function migrateMolecules(stored: Partial<MoleculeSettings> | undefined): MoleculeSettings {
  return { viewMode: stored?.viewMode === 'source' ? 'source' : 'type' }
}

function saveToStorage(viewer: ViewerSettings, molecules: MoleculeSettings): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ viewer, molecules }))
  } catch {
    // Best-effort only.
  }
}

export const useSettingsStore = defineStore('settings', () => {
  const stored = loadFromStorage()
  const viewer = ref<ViewerSettings>(stored.viewer)
  const molecules = ref<MoleculeSettings>(stored.molecules)

  // Persist on change: both sections share one storage key, so either one
  // changing must write the whole payload (the other would otherwise be lost).
  watch(
    [viewer, molecules],
    () => saveToStorage(viewer.value, molecules.value),
    { deep: true },
  )

  function resetViewer(): void {
    viewer.value = { ...DEFAULT_VIEWER }
  }

  return {
    viewer,
    molecules,
    resetViewer,
  }
})
