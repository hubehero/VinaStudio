import { defineStore } from 'pinia'
import { ref } from 'vue'

import type { DockingDefaults, ProjectDockingConfig, ScoringFunction } from '@/types/api'

/**
 * Docking-form values live here, not in the route component.
 *
 * Navigating between Docking and Results remounts the view; a component-local
 * form silently reset the protocol. The project serializer also reads this
 * store, so a saved project reproduces the run it describes.
 */
export const useDockingFormStore = defineStore('docking-form', () => {
  const scoring = ref<ScoringFunction>('vina')
  const exhaustiveness = ref(8)
  const nPoses = ref(20)
  const energyRange = ref(3.0)
  const minRmsd = ref(1.0)
  const maxEvals = ref(0)
  const cpu = ref(0)
  const seed = ref(0)
  const noRefine = ref(false)
  const verbosity = ref(1)
  const mapPathsRaw = ref('')
  const weightsRaw = ref('')
  const ensembleMode = ref(false)
  const ensembleReceptorIds = ref<string[]>([])
  let initialized = false

  /** Apply server defaults once, unless a project already supplied a protocol. */
  function applyDefaults(defaults: DockingDefaults): void {
    if (initialized) return
    scoring.value = defaults.scoring
    exhaustiveness.value = defaults.exhaustiveness
    nPoses.value = defaults.nPoses
    energyRange.value = defaults.energyRange
    minRmsd.value = defaults.minRmsd
    maxEvals.value = defaults.maxEvals
    cpu.value = defaults.cpu
    seed.value = defaults.seed
    noRefine.value = defaults.noRefine
    verbosity.value = defaults.verbosity
    initialized = true
  }

  function applyProject(config: ProjectDockingConfig | null | undefined): void {
    if (!config) return
    scoring.value = (config.scoring as ScoringFunction) || 'vina'
    exhaustiveness.value = config.exhaustiveness ?? 8
    nPoses.value = config.nPoses ?? 20
    energyRange.value = config.energyRange ?? 3.0
    minRmsd.value = config.minRmsd ?? 1.0
    maxEvals.value = config.maxEvals ?? 0
    cpu.value = config.cpu ?? 0
    seed.value = config.seed ?? 0
    noRefine.value = config.noRefine ?? false
    verbosity.value = config.verbosity ?? 1
    mapPathsRaw.value = config.mapPaths?.[0] ?? ''
    weightsRaw.value = (config.weights ?? []).join(',')
    // Ensemble choices are not part of the project format yet; do not leak
    // conformer ids from the previously open project.
    ensembleMode.value = false
    ensembleReceptorIds.value = []
    initialized = true
  }

  function reset(): void {
    scoring.value = 'vina'
    exhaustiveness.value = 8
    nPoses.value = 20
    energyRange.value = 3.0
    minRmsd.value = 1.0
    maxEvals.value = 0
    cpu.value = 0
    seed.value = 0
    noRefine.value = false
    verbosity.value = 1
    mapPathsRaw.value = ''
    weightsRaw.value = ''
    ensembleMode.value = false
    ensembleReceptorIds.value = []
    initialized = false
  }

  function snapshot(): ProjectDockingConfig {
    const weights = weightsRaw.value
      .split(',')
      .map((value) => Number(value.trim()))
      .filter((value) => Number.isFinite(value))
    return {
      scoring: scoring.value,
      exhaustiveness: exhaustiveness.value,
      nPoses: nPoses.value,
      energyRange: energyRange.value,
      minRmsd: minRmsd.value,
      maxEvals: maxEvals.value,
      cpu: cpu.value,
      seed: seed.value,
      noRefine: noRefine.value,
      verbosity: verbosity.value,
      mapPaths: mapPathsRaw.value.trim() ? [mapPathsRaw.value.trim()] : null,
      weights: weights.length ? weights : null,
    }
  }

  return {
    scoring,
    exhaustiveness,
    nPoses,
    energyRange,
    minRmsd,
    maxEvals,
    cpu,
    seed,
    noRefine,
    verbosity,
    mapPathsRaw,
    weightsRaw,
    ensembleMode,
    ensembleReceptorIds,
    applyDefaults,
    applyProject,
    reset,
    snapshot,
  }
})
