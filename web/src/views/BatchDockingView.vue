<script setup lang="ts">
import { Delete, Document, Download, Files } from '@element-plus/icons-vue'
import { ElButton, ElInputNumber, ElMessage, ElOption, ElProgress, ElSelect, ElTable, ElTableColumn } from 'element-plus'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { api } from '@/api/http'
import MoleculeSelect from '@/components/common/MoleculeSelect.vue'
import { useDockingStore } from '@/stores/docking'
import { useMoleculeStore } from '@/stores/molecules'
import { useBoxStore } from '@/stores/box'
import type { ScoringFunction, BatchLigandItem } from '@/types/api'
import { downloadTextFile } from '@/utils/download'

const { t } = useI18n()
const docking = useDockingStore()
const molecules = useMoleculeStore()
const box = useBoxStore()

// AutoDock4 is deliberately absent: it needs externally generated AutoGrid4
// maps and this form has no way to supply them, so offering it could only fail.
const scoringOptions: { value: ScoringFunction; label: string }[] = [
  { value: 'vina', label: 'Vina' },
  { value: 'vinardo', label: 'Vinardo' },
]

const scoring = ref<ScoringFunction>('vina')
const exhaustiveness = ref(8)
const nPoses = ref(20)
const energyRange = ref(3.0)
const minRmsd = ref(1.0)
const cpu = ref(0)
const seed = ref(0)
const noRefine = ref(false)

// Ligand list
const ligands = ref<BatchLigandItem[]>([])
const ligandInput = ref<string | null>(null)

const hasReceptor = computed(() => molecules.hasReceptor)
const hasLigands = computed(() => ligands.value.length > 0)

const canStart = computed(
  () => hasReceptor.value && hasLigands.value && !docking.batchIsRunning,
)

const statusLabel = computed(() => {
  const s = docking.batchStatusStr
  if (s === 'queued' || s === 'running' || s === 'completed' || s === 'failed' || s === 'cancelled') {
    return t(`docking.batch.status.${s}`)
  }
  return ''
})

function addLigandFromInput(): void {
  if (!ligandInput.value) return
  const path = ligandInput.value.trim()
  if (!path) return
  ligands.value.push({ ligandPath: path, ligandPdbqtString: null, label: path.split(/[\\/]/).pop() ?? path })
  ligandInput.value = null
}

/**
 * Usable ligands from the molecule manager that are not queued yet.
 *
 * The batch request takes prepared PDBQT only, which is exactly what a usable
 * ligand has on hand — so a prepared molecule joins the queue in one click
 * instead of asking the user to type a path.
 */
const managerLigands = computed(() =>
  molecules.usableLigands.filter((mol) => {
    const path = molecules.rigidPdbqtPath(mol)
    return path !== null && !ligands.value.some((l) => l.ligandPath === path)
  }),
)

function addFromManager(id: string): void {
  const mol = molecules.usableLigands.find((m) => m.id === id)
  const path = mol ? molecules.rigidPdbqtPath(mol) : null
  if (!mol || !path) return
  ligands.value.push({ ligandPath: path, ligandPdbqtString: null, label: mol.name })
}

function clearLigands(): void {
  ligands.value = []
}

async function startBatch(): Promise<void> {
  if (!canStart.value) return

  // Vina loads the receptor as PDBQT: the prepared rigid input, or the file
  // itself when it already is one. The source path is not it.
  const receptorPath = molecules.receptorPdbqtPath
  if (!receptorPath) {
    ElMessage.error(t('docking.noReceptor'))
    return
  }

  const result = await docking.startBatch({
    receptorPath,
    flexReceptorPath: molecules.flexReceptorPath,
    center: box.center as [number, number, number],
    size: box.size as [number, number, number],
    ligands: ligands.value,
    scoring: scoring.value,
    exhaustiveness: exhaustiveness.value,
    nPoses: nPoses.value,
    energyRange: energyRange.value,
    minRmsd: minRmsd.value,
    cpu: cpu.value,
    seed: seed.value,
    noRefine: noRefine.value,
  })

  if (!result) {
    ElMessage.error(t('docking.batch.failed'))
  }
}

async function cancelBatch(): Promise<void> {
  await docking.cancelBatch()
}

async function downloadBatchCsv(): Promise<void> {
  if (!docking.activeBatchId) return
  try {
    // The server already builds this CSV; a second copy here silently dropped
    // the pose_count column.
    const result = await api.exportBatchCsv(docking.activeBatchId)
    downloadTextFile(result.csv, result.filename, 'text/csv')
  } catch {
    ElMessage.error(t('docking.errorExportCsv'))
  }
}

function formatElapsed(ms: number | null): string {
  if (ms === null) return '-'
  const s = Math.floor(ms / 1000)
  const m = Math.floor(s / 60)
  const sec = s % 60
  return m > 0 ? `${m}m ${sec}s` : `${sec}s`
}
</script>

<template>
  <div class="batch-view">
    <section class="batch-view__main">
      <!-- Config Card -->
      <div class="vs-card">
        <div class="vs-card__header">
          <div>
            <div class="vs-card__title">{{ t('docking.batch.title') }}</div>
            <div class="vs-card__subtitle">{{ t('docking.batch.subtitle') }}</div>
          </div>
        </div>
        <div class="vs-card__body">
          <!-- Prerequisites -->
          <div v-if="!hasReceptor" class="prereqs">
            <div class="prereqs__item prereqs__item--missing">
              {{ t('docking.noReceptor') }}
            </div>
          </div>

          <!-- Config form (idle state) -->
          <div v-else-if="!docking.batchIsRunning && !docking.batchIsCompleted" class="form">
            <!-- Which receptor the batch docks against -->
            <div class="form__field">
              <label class="form__label">{{ t('molecules.typeReceptor') }}</label>
              <MoleculeSelect kind="receptor" />
            </div>

            <!-- Ligand list -->
            <div class="form__field">
              <label class="form__label">{{ t('docking.batch.addLigands') }}</label>
              <div class="ligand-input">
                <el-input
                  v-model="ligandInput"
                  :placeholder="t('docking.batch.placeholder')"
                  size="small"
                  @keyup.enter="addLigandFromInput"
                >
                  <template #append>
                    <el-button :icon="Document" @click="addLigandFromInput" />
                  </template>
                </el-input>
                <el-dropdown v-if="managerLigands.length > 0" trigger="click" @command="addFromManager">
                  <el-button size="small" :icon="Files">
                    {{ t('docking.batch.fromManager') }}
                  </el-button>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item
                        v-for="mol in managerLigands"
                        :key="mol.id"
                        :command="mol.id"
                      >
                        {{ mol.name }}
                      </el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </div>
              <div v-if="ligands.length > 0" class="ligand-list">
                <div v-for="(lig, idx) in ligands" :key="idx" class="ligand-item">
                  <span class="ligand-item__name">{{ lig.label }}</span>
                  <el-button text :icon="Delete" size="small" @click="ligands.splice(idx, 1)" />
                </div>
              </div>
              <div v-if="ligands.length > 0" class="ligand-actions">
                <el-button text size="small" @click="clearLigands">
                  {{ t('docking.batch.clearAll') }}
                </el-button>
                <span class="ligand-count">{{ ligands.length }} {{ t('docking.batch.total') }}</span>
              </div>
            </div>

            <!-- Scoring function -->
            <div class="form__field">
              <label class="form__label">{{ t('docking.scoringFunction') }}</label>
              <ElSelect v-model="scoring" size="small" style="width: 100%">
                <ElOption v-for="opt in scoringOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
              </ElSelect>
            </div>

            <!-- Exhaustiveness -->
            <div class="form__field">
              <label class="form__label">{{ t('docking.exhaustiveness') }}</label>
              <ElInputNumber v-model="exhaustiveness" :min="1" :max="512" size="small" style="width: 100%" />
            </div>

            <!-- Poses -->
            <div class="form__field">
              <label class="form__label">{{ t('docking.numPoses') }}</label>
              <ElInputNumber v-model="nPoses" :min="1" :max="50" size="small" style="width: 100%" />
            </div>

            <!-- Energy range -->
            <div class="form__field">
              <label class="form__label">{{ t('docking.energyRange') }}</label>
              <ElInputNumber v-model="energyRange" :min="1" :max="10" :step="0.5" size="small" style="width: 100%" />
            </div>

            <!-- Actions -->
            <div class="form__actions">
              <ElButton type="primary" :disabled="!canStart" @click="startBatch">
                {{ t('docking.batch.start') }}
              </ElButton>
            </div>
          </div>

          <!-- Progress (running state) -->
          <div v-else-if="docking.batchIsRunning" class="batch-progress">
            <div class="progress-header">
              <span class="status-badge status-badge--running">{{ statusLabel }}</span>
              <span class="progress-text">
                {{ docking.batchCompleted }} / {{ docking.batchTotal }}
                <template v-if="docking.batchFailed > 0">
                  ({{ docking.batchFailed }} {{ t('docking.batch.failedCount') }})
                </template>
              </span>
            </div>
            <ElProgress :percentage="docking.batchProgress" :status="docking.batchFailed > 0 ? 'exception' : undefined" />
            <div v-if="docking.batchCurrentLigand" class="current-ligand">
              {{ t('docking.batch.currentLigand') }}: {{ docking.batchCurrentLigand }}
            </div>
            <div class="form__actions">
              <ElButton type="danger" @click="cancelBatch">
                {{ t('docking.batch.cancel') }}
              </ElButton>
            </div>
          </div>

          <!-- Results (completed state) -->
          <div v-else-if="docking.batchIsCompleted" class="batch-results">
            <div class="results-summary">
              <div class="results-stat">
                <span class="results-stat__label">{{ t('docking.batch.total') }}</span>
                <span class="results-stat__value">{{ docking.batchTotal }}</span>
              </div>
              <div class="results-stat results-stat--success">
                <span class="results-stat__label">{{ t('docking.batch.completed') }}</span>
                <span class="results-stat__value">{{ docking.batchCompleted }}</span>
              </div>
              <div v-if="docking.batchFailed > 0" class="results-stat results-stat--error">
                <span class="results-stat__label">{{ t('docking.batch.failed') }}</span>
                <span class="results-stat__value">{{ docking.batchFailed }}</span>
              </div>
              <div v-if="docking.batchElapsedMs !== null" class="results-stat">
                <span class="results-stat__label">{{ t('docking.elapsed') }}</span>
                <span class="results-stat__value">{{ formatElapsed(docking.batchElapsedMs) }}</span>
              </div>
            </div>

            <!-- Results table -->
            <div class="results-table-wrap">
              <ElTable :data="docking.batchLigands" size="small" max-height="400">
                <ElTableColumn prop="ligandIndex" :label="'#'" width="50" />
                <ElTableColumn prop="label" :label="t('docking.batch.tableLabel')" min-width="120" />
                <ElTableColumn prop="status" :label="t('docking.batch.tableStatus')" width="100">
                  <template #default="{ row }">
                    <span :class="['status-badge', `status-badge--${row.status}`]">
                      {{ t(`docking.batch.status.${row.status}`) }}
                    </span>
                  </template>
                </ElTableColumn>
                <ElTableColumn :label="t('docking.batch.tableAffinity')" width="120">
                  <template #default="{ row }">
                    {{ row.affinity !== null ? row.affinity.toFixed(2) : '-' }}
                  </template>
                </ElTableColumn>
                <ElTableColumn :label="t('docking.batch.tableError')" min-width="150">
                  <template #default="{ row }">
                    <span v-if="row.error" class="error-text">{{ row.error }}</span>
                  </template>
                </ElTableColumn>
              </ElTable>
            </div>

            <div class="form__actions">
              <ElButton @click="docking.resetBatch()">
                {{ t('docking.batch.start') }} (New)
              </ElButton>
              <ElButton :icon="Download" @click="downloadBatchCsv">
                {{ t('docking.batch.exportCsv') }}
              </ElButton>
            </div>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.batch-view {
  display: grid;
  grid-template-columns: 1fr;
  gap: 16px;
  padding: 16px 18px;
  height: 100%;
  min-height: 0;
  overflow-y: auto;
}

.batch-view__main {
  max-width: 720px;
  margin: 0 auto;
  width: 100%;
}

.form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.form__field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.form__label {
  font-size: 12px;
  font-weight: 600;
  color: var(--vs-text);
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.form__actions {
  display: flex;
  gap: 8px;
  padding-top: 4px;
}

.prereqs {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 0;
}

.prereqs__item {
  font-size: 13px;
  color: var(--vs-text-faint);
}

.prereqs__item--missing {
  color: var(--vs-accent-amber);
}

/* Ligand list */
.ligand-input {
  display: flex;
  gap: 6px;
}

.ligand-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: 8px;
  max-height: 200px;
  overflow-y: auto;
}

.ligand-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 8px;
  border-radius: var(--vs-radius-sm);
  background: var(--vs-bg-sunken);
  border: 1px solid var(--vs-border);
  font-size: 12px;
}

.ligand-item__name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}

.ligand-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 4px;
}

.ligand-count {
  font-size: 12px;
  color: var(--vs-text-faint);
}

/* Progress */
.batch-progress {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.progress-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.progress-text {
  font-size: 13px;
  color: var(--vs-text);
}

.current-ligand {
  font-size: 12px;
  color: var(--vs-text-faint);
}

/* Status badges */
.status-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: var(--vs-radius-sm);
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
}

.status-badge--queued {
  background: var(--vs-bg-sunken);
  color: var(--vs-text-faint);
}

.status-badge--running {
  background: rgba(59, 130, 246, 0.1);
  color: #3b82f6;
}

.status-badge--completed {
  background: rgba(34, 197, 94, 0.1);
  color: #22c55e;
}

.status-badge--failed {
  background: rgba(239, 68, 68, 0.1);
  color: #ef4444;
}

/* Results */
.batch-results {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.results-summary {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}

.results-stat {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.results-stat__label {
  font-size: 11px;
  color: var(--vs-text-faint);
  text-transform: uppercase;
}

.results-stat__value {
  font-size: 18px;
  font-weight: 600;
  color: var(--vs-text);
}

.results-stat--success .results-stat__value {
  color: #22c55e;
}

.results-stat--error .results-stat__value {
  color: #ef4444;
}

.results-table-wrap {
  border: 1px solid var(--vs-border);
  border-radius: var(--vs-radius-sm);
  overflow: hidden;
}

.error-text {
  font-size: 11px;
  color: #ef4444;
}
</style>
