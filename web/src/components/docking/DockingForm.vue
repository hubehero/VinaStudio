<script setup lang="ts">
import { Download, RefreshRight, VideoPause, VideoPlay } from '@element-plus/icons-vue'
import { ElButton, ElInput, ElInputNumber, ElMessage, ElOption, ElProgress, ElSelect, ElSlider, ElSwitch } from 'element-plus'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import MoleculeSelect from '@/components/common/MoleculeSelect.vue'
import { downloadTextFile } from '@/utils/download'
import { useBoxStore } from '@/stores/box'
import { useDockingStore } from '@/stores/docking'
import { useMoleculeStore } from '@/stores/molecules'
import type { ScoringFunction } from '@/types/api'

const { t } = useI18n()
const docking = useDockingStore()
const molecules = useMoleculeStore()
const box = useBoxStore()

// AutoDock4 needs externally generated AutoGrid4 maps, so it only works when
// the user supplies the map prefix path via the mapPaths field.
const scoringOptions: { value: ScoringFunction; label: string }[] = [
  { value: 'vina', label: 'Vina' },
  { value: 'vinardo', label: 'Vinardo' },
  { value: 'ad4', label: 'AutoDock4' },
]

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

const hasReceptor = computed(() => molecules.hasReceptor)
const hasLigand = computed(() => molecules.hasLigand)

const canDock = computed(
  () => hasReceptor.value && hasLigand.value && !docking.isRunning
    && (scoring.value !== 'ad4' || mapPathsRaw.value.trim().length > 0),
)

const statusLabel = computed(() => {
  const s = docking.status
  if (s === 'queued' || s === 'running' || s === 'completed' || s === 'failed' || s === 'cancelled') {
    return t(`docking.status.${s}`)
  }
  return ''
})

function formatMs(ms: number | null): string {
  if (ms === null) return '—'
  if (ms < 1000) return `${ms}ms`
  const s = ms / 1000
  if (s < 60) return `${s.toFixed(1)}s`
  const m = Math.floor(s / 60)
  return `${m}m ${Math.round(s % 60)}s`
}

async function startDocking(): Promise<void> {
  if (!canDock.value) return

  const receptorPath = molecules.receptorPdbqtPath
  const ligandPath = molecules.ligandPdbqtPath
  if (!receptorPath || !ligandPath) {
    ElMessage.error(t('docking.errorNoPdbqt'))
    return
  }

  const params = {
    receptorPath,
    flexReceptorPath: molecules.flexReceptorPath,
    ligandPath,
    ligandPdbqtString: null,
    center: box.center as [number, number, number],
    size: box.size as [number, number, number],
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
    spacing: box.spacing,
    forceEvenVoxels: box.forceEvenVoxels,
    weights: weightsRaw.value.trim()
      ? weightsRaw.value.split(',').map((s) => parseFloat(s.trim())).filter((n) => !Number.isNaN(n))
      : null,
    mapPaths: mapPathsRaw.value.trim()
      ? [mapPathsRaw.value.trim()]
      : null,
  }

  const jobId = await docking.startDocking(params)
  if (!jobId) {
    ElMessage.error(t('docking.errorStartFailed'))
  }
}

function downloadPdbqt(): void {
  const pdbqt = docking.jobResult?.posesPdbqt
  if (pdbqt) downloadTextFile(pdbqt, 'docking_poses.pdbqt', 'chemical/x-pdbqt')
}

function downloadSdf(): void {
  const sdf = docking.jobResult?.posesSdf
  if (sdf) downloadTextFile(sdf, 'docking_poses.sdf', 'chemical/x-mdl-sdfile')
}
</script>

<template>
  <div class="vs-card">
    <div class="vs-card__header">
      <div>
        <div class="vs-card__title">{{ t('docking.title') }}</div>
        <div class="vs-card__subtitle">{{ t('docking.subtitle') }}</div>
      </div>
    </div>
    <div class="vs-card__body">
      <!-- Which molecules this run docks; switchable without leaving the view. -->
      <div class="inputs">
        <div class="inputs__row">
          <span class="inputs__label">{{ t('molecules.typeReceptor') }}</span>
          <MoleculeSelect kind="receptor" :disabled="docking.isRunning" />
        </div>
        <div class="inputs__row">
          <span class="inputs__label">{{ t('molecules.typeLigand') }}</span>
          <MoleculeSelect kind="ligand" :disabled="docking.isRunning" />
        </div>
      </div>

      <!-- Prerequisites -->
      <div v-if="!hasReceptor || !hasLigand" class="prereqs">
        <div v-if="!hasReceptor" class="prereqs__item prereqs__item--missing">
          {{ t('docking.noReceptor') }}
        </div>
        <div v-if="!hasLigand" class="prereqs__item prereqs__item--missing">
          {{ t('docking.noLigand') }}
        </div>
      </div>

      <!-- Form (idle state) -->
      <div v-else-if="!docking.isRunning && !docking.isCompleted" class="form">
        <div class="form__field">
          <label class="form__label">{{ t('docking.scoringFunction') }}</label>
          <ElSelect v-model="scoring" size="small" style="width: 100%">
            <ElOption v-for="opt in scoringOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
          </ElSelect>
        </div>

        <div class="form__field">
          <label class="form__label">{{ t('docking.exhaustiveness') }}</label>
          <ElInputNumber v-model="exhaustiveness" :min="1" :max="512" size="small" style="width: 100%" />
          <div class="form__hint">{{ t('docking.exhaustivenessNote') }}</div>
        </div>

        <div class="form__row">
          <div class="form__field form__field--half">
            <label class="form__label">{{ t('docking.numPoses') }}</label>
            <ElInputNumber v-model="nPoses" :min="1" :max="100" size="small" style="width: 100%" />
          </div>
          <div class="form__field form__field--half">
            <label class="form__label">{{ t('docking.energyRange') }}</label>
            <ElInputNumber v-model="energyRange" :min="0.1" :step="0.5" size="small" style="width: 100%" />
          </div>
        </div>

        <div class="form__row">
          <div class="form__field form__field--half">
            <label class="form__label">{{ t('docking.minRmsd') }}</label>
            <ElInputNumber v-model="minRmsd" :min="0" :step="0.1" size="small" style="width: 100%" />
          </div>
          <div class="form__field form__field--half">
            <label class="form__label">{{ t('docking.maxEvals') }}</label>
            <ElInputNumber v-model="maxEvals" :min="0" :step="1000" size="small" style="width: 100%" />
          </div>
        </div>

        <div class="form__row">
          <div class="form__field form__field--half">
            <label class="form__label">{{ t('docking.cpuCores') }}</label>
            <ElInputNumber v-model="cpu" :min="0" size="small" style="width: 100%" />
          </div>
          <div class="form__field form__field--half">
            <label class="form__label">{{ t('docking.seed') }}</label>
            <ElInputNumber v-model="seed" :min="0" size="small" style="width: 100%" />
          </div>
        </div>

        <div class="form__field form__inline">
          <ElSwitch v-model="noRefine" />
          <span class="form__option-label">{{ t('docking.noRefine') }}</span>
        </div>

        <div class="form__field">
          <label class="form__label">{{ t('docking.verbosity') }}: {{ verbosity }}</label>
          <ElSlider v-model="verbosity" :min="0" :max="2" :step="1" :show-tooltip="false" />
        </div>

        <div v-if="scoring === 'ad4'" class="form__field">
          <label class="form__label">{{ t('docking.mapPaths') }}</label>
          <ElInput v-model="mapPathsRaw" size="small" :placeholder="t('docking.mapPathsNote')" />
        </div>

        <div class="form__field">
          <label class="form__label">{{ t('docking.weights') }}</label>
          <ElInput v-model="weightsRaw" size="small" :placeholder="t('docking.weightsNote')" />
        </div>

        <ElButton type="primary" :icon="VideoPlay" :disabled="!canDock" style="width: 100%" @click="startDocking">
          {{ t('docking.startButton') }}
        </ElButton>
      </div>

      <!-- Running state -->
      <div v-if="docking.isRunning" class="running">
        <div class="running__header">
          <span class="running__status">{{ statusLabel }}</span>
          <span v-if="docking.stage" class="running__stage">{{ t(`docking.stage.${docking.stage}`) }}</span>
        </div>
        <ElProgress :percentage="docking.progress" :stroke-width="10" style="margin-bottom: 12px" />
        <ElButton type="danger" size="small" :icon="VideoPause" @click="docking.cancel()">
          {{ t('docking.cancelButton') }}
        </ElButton>
      </div>

      <!-- Completed state -->
      <div v-if="docking.isCompleted" class="completed">
        <div class="completed__header">
          <span class="completed__status">{{ t('docking.status.completed') }}</span>
          <span v-if="docking.elapsedMs !== null" class="completed__time">
            {{ t('docking.elapsed') }} {{ formatMs(docking.elapsedMs) }}
          </span>
        </div>
        <div v-if="docking.bestAffinity !== null" class="completed__best">
          {{ t('docking.bestAffinity') }}:
          <strong>{{ Number(docking.bestAffinity).toFixed(2) }}</strong> kcal/mol
        </div>
        <div class="completed__actions">
          <ElButton size="small" :icon="Download" @click="downloadPdbqt">{{ t('docking.exportPdbqt') }}</ElButton>
          <ElButton size="small" :icon="Download" @click="downloadSdf">{{ t('docking.exportSdf') }}</ElButton>
          <ElButton size="small" :icon="RefreshRight" @click="docking.reset()">{{ t('docking.resetButton') }}</ElButton>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.inputs {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 12px;
}

.inputs__row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.inputs__label {
  flex: none;
  width: 48px;
  font-size: 12px;
  color: var(--vs-text-muted);
}

.prereqs {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.prereqs__item {
  padding: 8px 12px;
  border-radius: var(--vs-radius);
  font-size: 13px;
}

.prereqs__item--missing {
  background: var(--vs-bg-sunken);
  color: var(--vs-text-muted);
  border: 1px dashed var(--vs-border);
}

.form {
  display: flex;
  flex-direction: column;
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

.form__row {
  display: flex;
  gap: 12px;
}

.form__inline {
  flex-direction: row;
  align-items: center;
}

.form__label {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--vs-text-muted);
}

.form__hint {
  font-size: 11px;
  color: var(--vs-text-faint);
  line-height: 1.4;
}

.form__option-label {
  font-size: 13px;
  margin-left: 8px;
}

.running {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.running__header {
  display: flex;
  align-items: center;
  gap: 10px;
}

.running__status {
  font-size: 14px;
  font-weight: 600;
  color: var(--vs-accent);
}

.running__stage {
  font-size: 12px;
  color: var(--vs-text-muted);
}

.completed {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.completed__header {
  display: flex;
  align-items: center;
  gap: 10px;
}

.completed__status {
  font-size: 14px;
  font-weight: 600;
  color: #67c23a;
}

.completed__time {
  font-size: 12px;
  color: var(--vs-text-muted);
}

.completed__best {
  font-size: 14px;
  color: var(--vs-text);
}

.completed__actions {
  display: flex;
  gap: 8px;
}
</style>
