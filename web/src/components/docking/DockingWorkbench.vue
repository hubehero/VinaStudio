<script setup lang="ts">
/**
 * Score / optimise / randomise the current pipeline ligand.
 *
 * This exposes the three ``POST /api/docking/{score,optimize,randomize}``
 * endpoints that the capability matrix advertises but had no UI entry.  All
 * three need receptor + ligand + box (the library ranks random conformers by
 * energy, so maps are never optional).
 */
import { Download } from '@element-plus/icons-vue'
import { ElButton, ElInputNumber, ElMessage, ElOption, ElSelect } from 'element-plus'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { api } from '@/api/http'
import { downloadTextFile } from '@/utils/download'
import { useBoxStore } from '@/stores/box'
import { useMoleculeStore } from '@/stores/molecules'
import type { ScoreResponse, OptimizeResponse, RandomizeResponse, ScoringFunction } from '@/types/api'

const { t } = useI18n()
const molecules = useMoleculeStore()
const box = useBoxStore()

const scoring = ref<ScoringFunction>('vina')
const optimizeMaxSteps = ref(0)
const randomizeMaxSteps = ref(10000)
const randomizeSeed = ref(0)

const loading = ref<'score' | 'optimize' | 'randomize' | null>(null)
const scoreResult = ref<ScoreResponse | null>(null)
const optimizeResult = ref<OptimizeResponse | null>(null)
const randomizeResult = ref<RandomizeResponse | null>(null)

const hasReceptor = computed(() => molecules.hasReceptor)
const hasLigand = computed(() => molecules.hasLigand)
const canRun = computed(() => hasReceptor.value && hasLigand.value && loading.value === null)

/** Shared request body for the three workbench endpoints. */
function baseBody() {
  return {
    receptorPath: molecules.receptorPdbqtPath!,
    flexReceptorPath: molecules.flexReceptorPath,
    ligandPath: molecules.ligandPdbqtPath,
    ligandPdbqtString: null as string | null,
    center: box.center,
    size: box.size,
    scoring: scoring.value,
    spacing: box.spacing,
    forceEvenVoxels: box.forceEvenVoxels,
  }
}

function clearResults(): void {
  scoreResult.value = null
  optimizeResult.value = null
  randomizeResult.value = null
}

async function handleScore(): Promise<void> {
  if (!canRun.value) return
  loading.value = 'score'
  clearResults()
  try {
    scoreResult.value = await api.scorePose({ ...baseBody(), unboundEnergy: null })
  } catch {
    ElMessage.error(t('docking.workbench.error'))
  } finally {
    loading.value = null
  }
}

async function handleOptimize(): Promise<void> {
  if (!canRun.value) return
  loading.value = 'optimize'
  clearResults()
  try {
    optimizeResult.value = await api.optimizePose({
      ...baseBody(),
      maxSteps: optimizeMaxSteps.value,
    })
  } catch {
    ElMessage.error(t('docking.workbench.error'))
  } finally {
    loading.value = null
  }
}

async function handleRandomize(): Promise<void> {
  if (!canRun.value) return
  loading.value = 'randomize'
  clearResults()
  try {
    randomizeResult.value = await api.randomizePose({
      ...baseBody(),
      maxSteps: randomizeMaxSteps.value,
      seed: randomizeSeed.value,
    })
  } catch {
    ElMessage.error(t('docking.workbench.error'))
  } finally {
    loading.value = null
  }
}

function downloadOptimized(): void {
  if (optimizeResult.value) {
    downloadTextFile(optimizeResult.value.ligandPdbqt, 'optimised.pdbqt', 'chemical/x-pdbqt')
  }
}

function downloadRandomized(): void {
  if (randomizeResult.value) {
    downloadTextFile(randomizeResult.value.ligandPdbqt, 'randomised.pdbqt', 'chemical/x-pdbqt')
  }
}
</script>

<template>
  <div v-if="hasReceptor && hasLigand" class="vs-card">
    <div class="vs-card__header">
      <div>
        <div class="vs-card__title">{{ t('docking.workbench.title') }}</div>
        <div class="vs-card__subtitle">{{ t('docking.workbench.subtitle') }}</div>
      </div>
    </div>
    <div class="vs-card__body workbench">
      <div class="form__field">
        <label class="form__label">{{ t('docking.scoringFunction') }}</label>
        <ElSelect v-model="scoring" size="small" style="width: 100%">
          <ElOption label="Vina" value="vina" />
          <ElOption label="Vinardo" value="vinardo" />
        </ElSelect>
      </div>

      <div class="workbench__actions">
        <ElButton
          type="primary" size="small"
          :disabled="!canRun" :loading="loading === 'score'"
          @click="handleScore"
        >
          {{ t('docking.workbench.score') }}
        </ElButton>
        <ElButton
          size="small"
          :disabled="!canRun" :loading="loading === 'optimize'"
          @click="handleOptimize"
        >
          {{ t('docking.workbench.optimize') }}
        </ElButton>
        <ElButton
          size="small"
          :disabled="!canRun" :loading="loading === 'randomize'"
          @click="handleRandomize"
        >
          {{ t('docking.workbench.randomize') }}
        </ElButton>
      </div>

      <div class="workbench__params">
        <div class="form__field form__field--half">
          <label class="form__label">{{ t('docking.workbench.seed') }}</label>
          <ElInputNumber v-model="randomizeSeed" :min="0" size="small" style="width: 100%" />
        </div>
        <div class="form__field form__field--half">
          <label class="form__label">{{ t('docking.workbench.maxSteps') }}</label>
          <ElInputNumber v-model="randomizeMaxSteps" :min="1" size="small" style="width: 100%" />
        </div>
      </div>

      <!-- Score result -->
      <div v-if="scoreResult" class="workbench__result">
        <div class="workbench__result-title">{{ t('docking.workbench.result') }}</div>
        <dl class="workbench__energy">
          <div class="workbench__energy-row"><dt>total</dt><dd>{{ scoreResult.total.toFixed(3) }}</dd></div>
          <div class="workbench__energy-row"><dt>inter</dt><dd>{{ scoreResult.inter.toFixed(3) }}</dd></div>
          <div class="workbench__energy-row"><dt>intra</dt><dd>{{ scoreResult.intra.toFixed(3) }}</dd></div>
          <div class="workbench__energy-row"><dt>torsions</dt><dd>{{ scoreResult.torsions.toFixed(3) }}</dd></div>
          <div class="workbench__energy-row"><dt>intra_best</dt><dd>{{ scoreResult.intra_best.toFixed(3) }}</dd></div>
        </dl>
      </div>

      <!-- Optimize result -->
      <div v-if="optimizeResult" class="workbench__result">
        <div class="workbench__result-title">
          {{ t('docking.workbench.result') }}: {{ optimizeResult.energy.toFixed(3) }} kcal/mol
        </div>
        <ElButton size="small" :icon="Download" @click="downloadOptimized">
          {{ t('docking.workbench.downloadPdbqt') }}
        </ElButton>
      </div>

      <!-- Randomize result -->
      <div v-if="randomizeResult" class="workbench__result">
        <div class="workbench__result-title">{{ t('docking.workbench.result') }}</div>
        <ElButton size="small" :icon="Download" @click="downloadRandomized">
          {{ t('docking.workbench.downloadPdbqt') }}
        </ElButton>
      </div>
    </div>
  </div>
</template>

<style scoped>
.workbench {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.workbench__actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.workbench__params {
  display: flex;
  gap: 12px;
}

.form__field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.form__field--half {
  flex: 1;
  min-width: 0;
}

.form__label {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--vs-text-muted);
}

.workbench__result {
  padding: 10px;
  border-radius: var(--vs-radius);
  background: var(--vs-bg-sunken);
  border: 1px solid var(--vs-border);
}

.workbench__result-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--vs-text-muted);
  margin-bottom: 6px;
}

.workbench__energy {
  margin: 0;
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 2px 12px;
  font-size: 11.5px;
}

.workbench__energy-row {
  display: flex;
  justify-content: space-between;
}

.workbench__energy-row dt {
  color: var(--vs-text-muted);
}

.workbench__energy-row dd {
  margin: 0;
  font-family: var(--vs-font-mono);
  color: var(--vs-text);
}
</style>
