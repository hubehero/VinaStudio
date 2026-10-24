<script setup lang="ts">
import { Aim, Document, MagicStick, Refresh, WarningFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import HelpLink from '@/components/HelpLink.vue'
import StatusPill from '@/components/StatusPill.vue'
import MoleculeSelect from '@/components/common/MoleculeSelect.vue'
import { useBoxStore } from '@/stores/box'
import { useMoleculeStore } from '@/stores/molecules'
import { useSiteScreeningStore } from '@/stores/site-screening'
import type { PocketCandidate, SiteRow } from '@/types/api'

/**
 * The search box panel.
 *
 * Every derived number — voxels, grid points, whether `write_maps` would accept
 * the box — comes from the backend, because those are Vina's rules and there
 * must be exactly one definition of them.
 */
const box = useBoxStore()
const molecules = useMoleculeStore()
const { t } = useI18n()

const extend = ref(4.0)
const configText = ref('')
const applyBusy = ref(false)

/**
 * Axis descriptors with literal indices, so indexing the centre and size tuples
 * stays typed as `number` rather than `number | undefined`.
 */
const AXES = [
  { key: 'x', index: 0 },
  { key: 'y', index: 1 },
  { key: 'z', index: 2 },
] as const

/** Ligand-ish sources are the ones autobox-from-ligand can use. */
const ligandSource = computed(
  () => molecules.pipelineLigand?.path ?? molecules.pipelineReceptor?.path ?? null,
)
const residueSource = computed(() => molecules.pipelineReceptor?.path ?? null)

onMounted(() => {
  if (!box.metrics) {
    void box.measure()
  }
})

async function autoboxFromLigand(): Promise<void> {
  const path = ligandSource.value
  if (!path) {
    return
  }
  if (await box.autoboxFromLigand(path, extend.value)) {
    ElMessage.success(t('box.autoboxDone', { n: box.autoboxPoints ?? 0 }))
  }
}

async function autoboxFromReceptor(): Promise<void> {
  const path = residueSource.value
  if (!path) {
    return
  }
  // No residue selection yet, so this boxes the whole receptor; the residue
  // picker arrives with the pocket-selection work in a later phase.
  if (await box.autoboxFromResidues(path, [], extend.value)) {
    ElMessage.success(t('box.autoboxDone', { n: box.autoboxPoints ?? 0 }))
  }
}

// -- candidate sites ---------------------------------------------------------
const pocketsAttempted = ref(false)

async function detectPockets(): Promise<void> {
  const path = residueSource.value
  if (!path) {
    return
  }
  pocketsAttempted.value = true
  // The list and the empty/error states are rendered inline; a toast would only
  // duplicate them.
  await box.detectPockets(path)
}

function usePocket(candidate: PocketCandidate): void {
  box.applyPocket(candidate)
  ElMessage.success(t('box.pockets.applied'))
}

// -- screening the candidates ------------------------------------------------
const screen = useSiteScreeningStore()
/** Coarse by design: a screen ranks sites, it does not produce final numbers. */
const screenExhaustiveness = ref(4)

const canScreen = computed(
  () => molecules.receptorPdbqtPath !== null && molecules.ligandPdbqtPath !== null,
)

async function runScreen(): Promise<void> {
  const receptorPath = molecules.receptorPdbqtPath
  const ligandPath = molecules.ligandPdbqtPath
  if (receptorPath === null || ligandPath === null) {
    return
  }
  // The candidates go in the order the list shows them, and each row's index is
  // its position here — that is how a row finds its box again.
  await screen.start({
    receptorPath,
    flexReceptorPath: molecules.flexReceptorPath ?? null,
    ligandPath,
    candidates: box.pockets.map((candidate, index) => ({
      index,
      label: `#${candidate.rank}`,
      center: candidate.center,
      size: candidate.size,
    })),
    exhaustiveness: screenExhaustiveness.value,
    nPoses: 5,
    seed: 0,
  })
}

function useScreenRow(row: SiteRow): void {
  const candidate = box.pockets[row.index]
  if (candidate !== undefined) {
    usePocket(candidate)
  }
}

async function exportConfig(): Promise<void> {
  try {
    configText.value = await box.exportConfig()
    ElMessage.success(t('box.configExported'))
  } catch {
    ElMessage.error(t('box.configExportError'))
  }
}

async function importConfig(): Promise<void> {
  if (!configText.value.trim()) {
    return
  }
  applyBusy.value = true
  try {
    if (await box.importConfig(configText.value)) {
      ElMessage.success(t('box.configImported'))
    }
  } finally {
    applyBusy.value = false
  }
}

function setCenterAxis(axis: 0 | 1 | 2, value: number | undefined): void {
  if (value === undefined || Number.isNaN(value)) {
    return
  }
  box.setCenterAxis(axis, value)
}

function setSizeAxis(axis: 0 | 1 | 2, value: number | undefined): void {
  if (value === undefined || Number.isNaN(value)) {
    return
  }
  box.setSizeAxis(axis, value)
}

/** Backend warnings are English API detail; known ones get the UI's copy. */
function warningText(warning: string): string {
  return warning.includes('voxel count is odd') ? t('box.oddVoxelWarning') : warning
}
</script>

<template>
  <div class="vs-card">
    <div class="vs-card__header">
      <div>
        <div class="vs-card__title">{{ t('box.title') }}</div>
        <div class="vs-card__subtitle">{{ t('box.subtitle') }}</div>
      </div>
      <StatusPill
        v-if="box.metrics"
        :state="box.canWriteMaps ? 'ok' : 'warn'"
        :label="`${box.gridCells.toLocaleString()} ${t('box.voxels')}`"
        :detail="`${box.metrics.volume.toFixed(0)} Å³`"
      />
    </div>

    <div class="vs-card__body">
      <el-alert
        v-if="box.error"
        class="notice"
        type="error"
        :closable="false"
        show-icon
        :title="box.error"
      />

      <!-- Which molecules the box is drawn against; also the autobox sources. -->
      <div class="inputs">
        <div class="inputs__row">
          <span class="inputs__label">{{ t('molecules.typeReceptor') }}</span>
          <MoleculeSelect kind="receptor" />
        </div>
        <div class="inputs__row">
          <span class="inputs__label">{{ t('molecules.typeLigand') }}</span>
          <MoleculeSelect kind="ligand" />
        </div>
      </div>

      <div class="grid">
        <div class="grid__label">{{ t('box.center') }}</div>
        <div class="grid__fields">
          <el-input-number
            v-for="axis in AXES"
            :key="`c-${axis.key}`"
            :model-value="box.center[axis.index]"
            size="small"
            :step="0.5"
            :precision="3"
            :controls="false"
            :data-test="`box-center-${axis.key}`"
            @update:model-value="(value: number | undefined) => setCenterAxis(axis.index, value)"
          />
        </div>
        <div class="grid__label">{{ t('box.size') }}</div>
        <div class="grid__fields">
          <el-input-number
            v-for="axis in AXES"
            :key="`s-${axis.key}`"
            :model-value="box.size[axis.index]"
            size="small"
            :step="1"
            :min="1"
            :precision="3"
            :controls="false"
            :data-test="`box-size-${axis.key}`"
            @update:model-value="(value: number | undefined) => setSizeAxis(axis.index, value)"
          />
        </div>
        <div class="grid__label">{{ t('box.spacing') }}</div>
        <div class="grid__fields grid__fields--single">
          <el-input-number
            v-model="box.spacing"
            size="small"
            :step="0.025"
            :min="0.05"
            :precision="4"
            :controls="false"
            data-test="box-spacing"
          />
          <span class="vs-faint unit">Å</span>
        </div>
      </div>

      <div class="derived">
        <div class="derived__row">
          <span class="vs-muted">{{ t('box.voxelsPerAxis') }}</span>
          <span class="vs-mono">{{ box.voxels.join(' × ') }}</span>
        </div>
        <div class="derived__row">
          <span class="vs-muted">{{ t('box.gridPoints') }}</span>
          <span class="vs-mono">{{ box.metrics?.gridPoints.join(' × ') ?? '—' }}</span>
        </div>
        <div class="derived__row">
          <span class="vs-muted">{{ t('box.writable') }}</span>
          <StatusPill
            :state="box.canWriteMaps ? 'ok' : 'warn'"
            :label="box.canWriteMaps ? t('box.writableYes') : t('box.writableNo')"
          />
        </div>
        <div class="derived__row">
          <span class="vs-muted">{{ t('box.forceEvenVoxels') }}</span>
          <el-switch v-model="box.forceEvenVoxels" size="small" />
        </div>
        <p class="vs-faint force-even-note">{{ t('box.forceEvenNote') }}</p>
      </div>

      <el-alert
        v-for="warning in box.warnings"
        :key="warning"
        class="notice"
        type="warning"
        :closable="false"
        show-icon
        :title="warningText(warning)"
      />

      <el-divider />

      <div class="autobox">
        <div class="autobox__head">
          <span>{{ t('box.autobox') }}</span>
          <div class="autobox__extend">
            <span class="vs-faint">{{ t('box.extend') }}</span>
            <el-input-number
              v-model="extend"
              size="small"
              :step="1"
              :min="0"
              :precision="1"
              :controls="false"
              data-test="box-extend"
            />
          </div>
        </div>
        <p class="vs-faint autobox__note">{{ t('box.extendNote') }}</p>
        <div class="autobox__actions">
          <el-button
            size="small"
            :icon="MagicStick"
            :disabled="!ligandSource"
            :loading="box.measuring"
            data-test="autobox-ligand"
            @click="autoboxFromLigand"
          >
            {{ t('box.fromLigand') }}
          </el-button>
          <el-button
            size="small"
            :icon="MagicStick"
            :disabled="!residueSource"
            :loading="box.measuring"
            data-test="autobox-receptor"
            @click="autoboxFromReceptor"
          >
            {{ t('box.fromReceptor') }}
          </el-button>
        </div>
        <div v-if="box.autoboxSource" class="vs-faint autobox__source">
          <el-icon><WarningFilled /></el-icon>
          {{ t('box.autoboxSource', { points: box.autoboxPoints ?? 0 }) }}
        </div>
      </div>

      <el-divider />

      <!-- Candidate sites: for a receptor with no known ligand to box around. -->
      <div class="pockets">
        <div class="pockets__head">
          <span>{{ t('box.pockets.title') }}</span>
          <el-button
            size="small"
            :icon="Aim"
            :disabled="!residueSource"
            :loading="box.pocketsLoading"
            data-test="detect-pockets"
            @click="detectPockets"
          >
            {{ t('box.pockets.detect') }}
          </el-button>
        </div>
        <p class="vs-faint pockets__note">{{ t('box.pockets.hint') }}</p>
        <p v-if="!residueSource" class="vs-faint pockets__note">
          {{ t('box.pockets.noReceptor') }}
        </p>
        <p v-if="box.pocketsError" class="pockets__error">
          {{ t('box.pockets.failed') }}: {{ box.pocketsError }}
        </p>
        <p
          v-else-if="pocketsAttempted && box.pockets.length === 0"
          class="vs-faint pockets__note"
        >
          {{ t('box.pockets.empty') }}
        </p>
        <div
          v-if="box.pocketsError || (pocketsAttempted && box.pockets.length === 0)"
          class="pockets__help"
        >
          <HelpLink topic="noSiteFound" />
        </div>
        <ol v-else-if="box.pockets.length > 0" class="pockets__list">
          <li
            v-for="candidate in box.pockets"
            :key="candidate.rank"
            class="pockets__row"
            :title="
              t('box.pockets.detail', {
                volume: Math.round(candidate.volume),
                spheres: candidate.spheres,
                apolar: (candidate.apolarFraction * 100).toFixed(0),
              })
            "
          >
            <span class="pockets__rank">#{{ candidate.rank }}</span>
            <span class="pockets__score">{{ candidate.score.toFixed(2) }}</span>
            <span class="vs-mono pockets__centre">
              {{ candidate.center.map((value) => value.toFixed(1)).join(', ') }}
            </span>
            <el-button text size="small" type="primary" @click="usePocket(candidate)">
              {{ t('box.pockets.use') }}
            </el-button>
          </li>
        </ol>

        <!-- The geometric order is a guess; docking each box is the test. -->
        <div v-if="box.pockets.length > 0" class="screen">
          <div class="screen__head">
            <span class="vs-faint">{{ t('box.pockets.screenTitle') }}</span>
            <el-button
              size="small"
              type="primary"
              :disabled="!canScreen"
              :loading="screen.running"
              data-test="screen-sites"
              @click="runScreen"
            >
              {{ t('box.pockets.screenRun') }}
            </el-button>
            <el-button v-if="screen.running" text size="small" @click="screen.cancel()">
              {{ t('box.pockets.screenCancel') }}
            </el-button>
          </div>

          <div class="screen__effort">
            <span>{{ t('box.pockets.screenExhaustiveness') }}</span>
            <el-input-number
              v-model="screenExhaustiveness"
              :min="1"
              :max="64"
              size="small"
              controls-position="right"
            />
          </div>

          <p v-if="!canScreen" class="vs-faint pockets__note">
            {{ t('box.pockets.screenNeeds') }}
          </p>
          <p v-if="screen.running" class="screen__progress">
            {{ t('box.pockets.screenProgress', { done: screen.done, total: screen.total }) }}
            <span v-if="screen.status?.currentLabel" class="vs-mono">
              · {{ screen.status.currentLabel }}
            </span>
          </p>
          <p v-if="screen.error" class="pockets__error">{{ screen.error }}</p>

          <table v-if="screen.rows.length > 0" class="screen__table">
            <thead>
              <tr>
                <th>{{ t('box.pockets.screenRank') }}</th>
                <th>{{ t('box.pockets.screenBox') }}</th>
                <th>{{ t('box.pockets.screenAffinity') }}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in screen.rows"
                :key="row.index"
                :class="{ 'screen__row--best': row.rank === 1 }"
              >
                <td>{{ row.rank ?? '—' }}</td>
                <td class="vs-mono">#{{ row.index + 1 }}</td>
                <td class="vs-mono">
                  <template v-if="row.bestAffinity !== null">
                    {{ row.bestAffinity.toFixed(1) }}
                  </template>
                  <span v-else-if="row.error" class="vs-faint">
                    {{ t('box.pockets.screenFailed') }}
                  </span>
                  <template v-else>—</template>
                </td>
                <td>
                  <el-button
                    v-if="row.rank !== null"
                    text
                    size="small"
                    type="primary"
                    @click="useScreenRow(row)"
                  >
                    {{ t('box.pockets.use') }}
                  </el-button>
                </td>
              </tr>
            </tbody>
          </table>
          <p v-if="screen.rows.length > 0" class="vs-faint pockets__note">
            {{ t('box.pockets.screenCaveat') }}
          </p>
        </div>
      </div>

      <el-divider />

      <div class="config">
        <div class="config__head">
          <span>{{ t('box.config') }}</span>
          <div>
            <el-button size="small" text :icon="Document" @click="exportConfig">
              {{ t('box.export') }}
            </el-button>
            <el-button
              size="small"
              text
              :icon="Refresh"
              :loading="applyBusy"
              @click="importConfig"
            >
              {{ t('box.import') }}
            </el-button>
          </div>
        </div>
        <el-input
          v-model="configText"
          type="textarea"
          :rows="5"
          spellcheck="false"
          :placeholder="t('box.configPlaceholder')"
          class="config__area"
        />
      </div>

      <el-button class="reset" size="small" :icon="Aim" @click="box.reset">
        {{ t('box.reset') }}
      </el-button>
    </div>
  </div>
</template>

<style scoped>
.notice {
  margin-top: 12px;
}

.inputs {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 12px;
  margin-bottom: 14px;
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

.grid {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.grid__label {
  font-size: 12px;
  color: var(--vs-text-muted);
}

.grid__fields {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.grid__fields--single {
  grid-template-columns: 1fr auto;
  align-items: center;
}

.unit {
  font-size: 12px;
}

:deep(.grid__fields .el-input__inner) {
  font-family: var(--vs-font-mono);
  font-size: 12px;
  text-align: center;
}

.derived {
  margin-top: 14px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.derived__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  font-size: 12.5px;
}

.force-even-note {
  margin: -2px 0 0;
  font-size: 11px;
  line-height: 1.5;
}

.autobox__head,
.config__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--vs-text-muted);
}

.autobox__extend {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 400;
}

.autobox__extend :deep(.el-input) {
  width: 74px;
}

.autobox__note {
  margin: 6px 0 10px;
  font-size: 11.5px;
  line-height: 1.6;
}

.autobox__actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.autobox__source {
  display: flex;
  align-items: center;
  gap: 5px;
  margin-top: 8px;
  font-size: 11.5px;
}

.config__area {
  margin-top: 8px;
}

.config__area :deep(.el-textarea__inner) {
  font-family: var(--vs-font-mono);
  font-size: 11.5px;
}

.reset {
  margin-top: 14px;
}

/* -- candidate sites -------------------------------------------------------- */

.pockets__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.pockets__note {
  margin: 6px 0 0;
  line-height: 1.5;
}

.pockets__error {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--vs-danger);
}

.pockets__list {
  list-style: none;
  margin: 8px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.pockets__row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 2px;
  border-radius: var(--vs-radius-sm);
  font-size: 12px;
}

.pockets__row:hover {
  background: var(--vs-bg-sunken);
}

.pockets__rank {
  flex: none;
  width: 22px;
  color: var(--vs-text-muted);
  font-variant-numeric: tabular-nums;
}

.pockets__score {
  flex: none;
  width: 34px;
  text-align: right;
  color: var(--vs-accent);
  font-variant-numeric: tabular-nums;
}

.pockets__centre {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--vs-text-faint);
}

.screen {
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px dashed var(--vs-border);
}

.screen__head {
  display: flex;
  align-items: center;
  gap: 8px;
}

.screen__head > span {
  flex: 1;
  min-width: 0;
}

.screen__effort {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-top: 8px;
  font-size: 12px;
  color: var(--vs-text-muted);
}

.screen__effort :deep(.el-input-number) {
  width: 92px;
}

.screen__progress {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--vs-text-muted);
}

.screen__table {
  width: 100%;
  margin-top: 8px;
  border-collapse: collapse;
  font-size: 12px;
}

.screen__table th {
  text-align: left;
  font-weight: 500;
  color: var(--vs-text-faint);
  padding-bottom: 4px;
}

.screen__table td {
  padding: 3px 4px 3px 0;
  border-top: 1px solid var(--vs-border);
  font-variant-numeric: tabular-nums;
}

/* The winning row is the answer the screen was run for. */
.screen__row--best td {
  color: var(--vs-accent);
  font-weight: 500;
}

:deep(.el-divider) {
  margin: 16px 0;
}
</style>
