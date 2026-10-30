<script setup lang="ts">
import { Download, FolderAdd, Refresh } from '@element-plus/icons-vue'
import type { Column } from 'element-plus'
import {
  ElAlert,
  ElAutoResizer,
  ElButton,
  ElDrawer,
  ElEmpty,
  ElInput,
  ElInputNumber,
  ElMessage,
  ElOption,
  ElProgress,
  ElSelect,
  ElTable,
  ElTableColumn,
  ElTableV2,
} from 'element-plus'
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { api } from '@/api/http'
import MoleculeSelect from '@/components/common/MoleculeSelect.vue'
import CatalogSelectionDialog from '@/components/panels/catalog/CatalogSelectionDialog.vue'
import ScreeningImportDialog from '@/components/screening/ScreeningImportDialog.vue'
import { useBoxStore } from '@/stores/box'
import { useMoleculeStore } from '@/stores/molecules'
import { useScreeningStore } from '@/stores/screening'
import type { CatalogSelection, RankingRow, RankingSortBy, ScoringFunction } from '@/types/api'
import { downloadTextFile } from '@/utils/download'

const { t } = useI18n()
const screening = useScreeningStore()
const molecules = useMoleculeStore()
const box = useBoxStore()

// AutoDock4 mirrors the batch form: no AutoGrid4 maps can be supplied here.
const scoringOptions: { value: ScoringFunction; label: string }[] = [
  { value: 'vina', label: 'Vina' },
  { value: 'vinardo', label: 'Vinardo' },
]

const importOpen = ref(false)
const entriesExpanded = ref(false)
const starting = ref(false)
const selectionOpen = ref(false)
const selection = ref<CatalogSelection | null>(null)

// -- config form (BatchDockingView field block, no ligand list) -------------
const scoring = ref<ScoringFunction>('vina')
const exhaustiveness = ref(8)
const nPoses = ref(20)
const energyRange = ref(3.0)

const cpuCount = ref<number | null>(null)
const parallelism = ref<number | null>(null)
const parallelismMax = computed(() => Math.min(4, Math.max(1, (cpuCount.value ?? 1) - 1)))

onMounted(async () => {
  void screening.loadLibraries()
  void screening.loadRuns()
  try {
    cpuCount.value = (await api.vinaInfo()).cpuCount
    parallelism.value = parallelismMax.value
  } catch {
    /* keep null: control disabled, payload omits the key, server default */
  }
})

// One library is the common first-run case: preselect it so the user lands on
// entries instead of an empty select. Multiple libraries stay an explicit choice.
watch(
  () => screening.libraries,
  (libraries) => {
    if (selection.value === null && screening.activeLibraryName === null && libraries.length === 1) {
      void screening.selectLibrary(libraries[0]!.name)
    }
  },
  { deep: true },
)

onUnmounted(() => {
  screening.stopPolling()
})

const hasReceptor = computed(() => molecules.hasReceptor)
/** Config card hides while the watched run is live (design §4). */
const activeRunning = computed(() => screening.runStatus?.status === 'running')
const hasRunSource = computed(
  () => (selection.value !== null && !selection.value.stale) || screening.activeLibraryName !== null,
)
const canStart = computed(
  () =>
    hasRunSource.value &&
    hasReceptor.value &&
    parallelism.value !== null &&
    !starting.value,
)
const startTitle = computed<string | undefined>(() => {
  if (!hasRunSource.value) return t('screening.needLibrary')
  if (!hasReceptor.value) return t('docking.noReceptor')
  if (parallelism.value === null) return t('docking.batch.parallelismUnavailable')
  return undefined
})

const coord = (value: number | undefined): string =>
  typeof value === 'number' ? value.toFixed(2) : '—'
const boxLine = computed(() =>
  t('screening.boxLine', {
    cx: coord(box.center[0]),
    cy: coord(box.center[1]),
    cz: coord(box.center[2]),
    sx: coord(box.size[0]),
    sy: coord(box.size[1]),
    sz: coord(box.size[2]),
  }),
)

async function startScreening(): Promise<void> {
  if (!canStart.value) return
  const library = screening.activeLibraryName
  const selected = selection.value
  const receptorPath = molecules.receptorPdbqtPath
  if ((library === null && selected === null) || receptorPath === null) {
    ElMessage.error(t('docking.noReceptor'))
    return
  }
  starting.value = true
  try {
    await screening.startRun({
      ...(selected ? { selectionId: selected.id } : { library: library! }),
      receptorPath,
      flexReceptorPath: molecules.flexReceptorPath,
      center: box.center as [number, number, number],
      size: box.size as [number, number, number],
      scoring: scoring.value,
      exhaustiveness: exhaustiveness.value,
      nPoses: nPoses.value,
      energyRange: energyRange.value,
      cpu: 0,
      seed: 0,
      ...(parallelism.value != null ? { parallelism: parallelism.value } : {}),
    })
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : t('screening.startFailed'))
  } finally {
    starting.value = false
  }
}

// -- library card ------------------------------------------------------------
function onLibraryChange(name: string): void {
  entriesExpanded.value = false
  selection.value = null
  void screening.selectLibrary(name)
}

function onSelectionPicked(picked: CatalogSelection): void {
  selection.value = picked
  ElMessage.success(t('screening.selectionReady', { n: picked.memberCount }))
}

function clearSelection(): void {
  selection.value = null
}

async function onImported(name: string): Promise<void> {
  importOpen.value = false
  await screening.loadLibraries()
  await screening.selectLibrary(name)
}

const libMeta = computed(() => {
  const detail = screening.libraryDetail
  if (detail === null) return ''
  // LibraryDetail has no prepared count; it lives on the summary row.
  const summary = screening.libraries.find((lib) => lib.name === detail.name)
  const prepared =
    summary !== undefined ? ` · ${t('screening.libPrepared', { n: summary.prepared })}` : ''
  const name = detail.displayName || detail.name
  return `${name} · ${t('screening.libTotal', { n: detail.total })}${prepared}`
})

const libraryPreview = computed(() => {
  const entries = screening.libraryDetail?.entries ?? []
  return { names: entries.slice(0, 6).map((entry) => entry.name), extra: Math.max(0, entries.length - 6) }
})

// -- rows preformatted for the zero-slot virtual tables (design §4) ----------
type Tone = '' | 'pass' | 'warn' | 'danger'

type EntryRow = {
  index: string
  name: string
  molWt: string
  qed: string
  lipinski: string
  prepare: string
  qedTone: 'has' | 'none'
  lipTone: Tone
  prepTone: 'none' | 'done' | 'failed'
}

type RankRow = {
  rank: string
  rankValue: number
  name: string
  affinity: string
  nPoses: string
  qed: string
  lipinski: string
  affTone: 'has' | 'none'
  qedTone: 'has' | 'none'
  lipTone: Tone
}

function lipTone(violations: number | null): Tone {
  if (violations === null) return ''
  if (violations === 0) return 'pass'
  return violations <= 2 ? 'warn' : 'danger'
}

const entryRows = computed<EntryRow[]>(() =>
  (screening.libraryDetail?.entries ?? []).map((entry) => ({
    index: String(entry.index),
    name: entry.name,
    molWt: entry.molWt !== null ? entry.molWt.toFixed(2) : '—',
    qed: entry.qed !== null ? entry.qed.toFixed(2) : '—',
    lipinski: entry.lipinskiViolations !== null ? String(entry.lipinskiViolations) : '—',
    prepare:
      entry.prepare === 'done'
        ? t('screening.prepareDone')
        : entry.prepare === 'failed'
          ? t('screening.prepareFailed')
          : t('screening.prepareNone'),
    qedTone: entry.qed !== null ? 'has' : 'none',
    lipTone: lipTone(entry.lipinskiViolations),
    prepTone: entry.prepare,
  })),
)

const nameFilter = ref('')
const detailRank = ref<RankingRow | null>(null)
const detailOpen = computed({
  get: () => detailRank.value !== null,
  set: (value: boolean) => {
    if (!value) detailRank.value = null
  },
})

const rankRows = computed<RankRow[]>(() => {
  const needle = nameFilter.value.trim().toLowerCase()
  const rows =
    needle === ''
      ? screening.ranking
      : screening.ranking.filter((row) => row.name.toLowerCase().includes(needle))
  return rows.map((row) => ({
    rank: String(row.rank),
    rankValue: row.rank,
    name: row.name,
    affinity: row.affinity !== null ? row.affinity.toFixed(2) : '—',
    nPoses: row.nPoses !== null ? String(row.nPoses) : '—',
    qed: row.qed !== null ? row.qed.toFixed(2) : '—',
    lipinski: row.lipinskiViolations !== null ? String(row.lipinskiViolations) : '—',
    affTone: row.affinity !== null ? 'has' : 'none',
    qedTone: row.qed !== null ? 'has' : 'none',
    lipTone: lipTone(row.lipinskiViolations),
  }))
})

/** Cell classes come from the preformatted tone fields (Column.class getter). */
function numClass(has: boolean): string {
  return has ? 'scr-num scr-num--has' : 'scr-num scr-num--none'
}
function plainNumClass(has: boolean): string {
  return has ? 'scr-num' : 'scr-num scr-num--none'
}
function lipClass(tone: Tone): string {
  return tone === '' ? '' : `scr-lip scr-lip--${tone}`
}
function prepClass(tone: 'none' | 'done' | 'failed'): string {
  return `scr-prep scr-prep--${tone}`
}

const entryColumns = computed<Column<EntryRow>[]>(() => [
  { title: t('screening.colIndex'), dataKey: 'index', width: 64 },
  { title: t('screening.colName'), dataKey: 'name', width: 280 },
  { title: t('screening.colMw'), dataKey: 'molWt', width: 96, align: 'right' },
  {
    title: t('screening.colQed'),
    dataKey: 'qed',
    width: 96,
    align: 'right',
    class: (params) => plainNumClass(params.rowData.qedTone === 'has'),
  },
  {
    title: t('screening.colLipinski'),
    dataKey: 'lipinski',
    width: 110,
    align: 'right',
    class: (params) => lipClass(params.rowData.lipTone),
  },
  {
    title: t('screening.colPrepare'),
    dataKey: 'prepare',
    width: 96,
    class: (params) => prepClass(params.rowData.prepTone),
  },
])

const rankRowEvents = {
  onClick: ({ rowData }: { rowData: { rankValue: number } }) => {
    detailRank.value = screening.ranking.find((row) => row.rank === rowData.rankValue) ?? null
  },
}

const rankColumns = computed<Column<RankRow>[]>(() => [
  { title: t('screening.colRank'), dataKey: 'rank', width: 64 },
  { title: t('screening.colName'), dataKey: 'name', width: 280 },
  {
    title: t('screening.colAffinity'),
    dataKey: 'affinity',
    width: 110,
    align: 'right',
    class: (params) => numClass(params.rowData.affTone === 'has'),
  },
  { title: t('screening.colPoses'), dataKey: 'nPoses', width: 88, align: 'right' },
  {
    title: t('screening.colQed'),
    dataKey: 'qed',
    width: 96,
    align: 'right',
    class: (params) => plainNumClass(params.rowData.qedTone === 'has'),
  },
  {
    title: t('screening.colLipinski'),
    dataKey: 'lipinski',
    width: 110,
    align: 'right',
    class: (params) => lipClass(params.rowData.lipTone),
  },
])

// -- rank toolbar ------------------------------------------------------------
const sortOptions: { value: RankingSortBy; labelKey: string }[] = [
  { value: 'affinity', labelKey: 'screening.sortAffinity' },
  { value: 'qed', labelKey: 'screening.sortQed' },
  { value: 'lipinski', labelKey: 'screening.sortLipinski' },
]

const topOptions = [100, 500, 1000]

function onSortChange(value: RankingSortBy): void {
  screening.rankingSortBy = value
  void screening.loadRanking()
}

function onTopChange(value: number): void {
  screening.rankingTop = value
  void screening.loadRanking()
}

async function exportRanking(): Promise<void> {
  try {
    const result = await screening.exportRankingCsv()
    downloadTextFile(result.csv, result.filename, 'text/csv')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : t('screening.rankingFailed'))
  }
}

// -- runs table --------------------------------------------------------------
// Slot rows are typed DefaultRow; take only the id so call sites stay honest.
function onRunRowClick(jobId: string): void {
  void screening.selectRun(jobId)
}

async function onResume(jobId: string): Promise<void> {
  try {
    await screening.resumeRun(jobId)
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : String(error))
  }
}

async function onCancelRun(jobId: string): Promise<void> {
  try {
    await screening.cancelRun(jobId)
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : String(error))
  }
}

/** Historical jobs may carry a bad counter; never render >100% to the user. */
function progressPercent(value: number | null | undefined): number {
  return Math.min(100, Math.max(0, Math.round(value ?? 0)))
}

function statusLabel(status: string): string {
  return t(`docking.status.${status}`)
}
</script>

<template>
  <div class="vs-page">
    <div class="vs-page__head">
      <div>
        <h1 class="vs-page__title">{{ t('screening.title') }}</h1>
        <p class="vs-page__subtitle">{{ t('screening.subtitle') }}</p>
      </div>
    </div>

    <!-- ① Library card -->
    <section class="vs-card">
      <div class="vs-card__header">
        <div class="screening-libbar">
          <el-select
            :model-value="screening.activeLibraryName ?? ''"
            :placeholder="t('screening.libs')"
            size="small"
            @change="onLibraryChange"
          >
            <el-option
              v-for="lib in screening.libraries"
              :key="lib.name"
              :label="lib.displayName || lib.name"
              :value="lib.name"
            />
          </el-select>
          <el-button
            size="small"
            type="primary"
            :icon="FolderAdd"
            :loading="screening.librariesLoading"
            @click="importOpen = true"
          >
            {{ t('screening.import') }}
          </el-button>
          <el-button size="small" @click="selectionOpen = true">
            {{ t('screening.fromCatalogPicker') }}
          </el-button>
          <el-button
            size="small"
            :disabled="screening.libraryDetail === null || entryRows.length === 0"
            @click="entriesExpanded = !entriesExpanded"
          >
            {{ entriesExpanded ? t('screening.hideEntries') : t('screening.showEntries') }}
          </el-button>
        </div>
      </div>
      <div
        class="vs-card__body"
        v-loading="screening.librariesLoading || screening.libraryLoading"
      >
        <div v-if="selection" class="screening-selection">
          <span>{{ t('screening.selectionReady', { n: selection.memberCount }) }}</span>
          <span v-if="selection.stale" class="selection-missing">
            {{ t('selection.stale', { live: selection.liveMemberCount ?? 0, expected: selection.memberCount }) }}
          </span>
          <el-button text size="small" @click="clearSelection">{{ t('common.clear') }}</el-button>
        </div>
        <el-alert
          v-if="!selection && screening.librariesError"
          type="error"
          :closable="false"
          show-icon
          :title="t('screening.libsFailed')"
        >
          <template #default>
            <el-button size="small" :icon="Refresh" @click="screening.loadLibraries()">
              {{ t('common.refresh') }}
            </el-button>
          </template>
        </el-alert>
        <el-empty
          v-else-if="!selection && screening.libraries.length === 0"
          :description="t('screening.entriesEmpty')"
          :image-size="72"
        />
        <template v-else-if="!selection">
          <div v-if="libMeta !== ''" class="screening-libmeta">{{ libMeta }}</div>
          <div v-if="libraryPreview.names.length > 0" class="screening-preview">
            <span v-for="name in libraryPreview.names" :key="name">{{ name }}</span>
            <span v-if="libraryPreview.extra > 0">+{{ libraryPreview.extra }}</span>
          </div>
          <el-alert
            v-if="screening.libraryError"
            type="error"
            :closable="false"
            show-icon
            :title="t('screening.libsFailed')"
          >
            <template #default>
              <el-button
                v-if="screening.activeLibraryName !== null"
                size="small"
                :icon="Refresh"
                @click="screening.selectLibrary(screening.activeLibraryName)"
              >
                {{ t('common.refresh') }}
              </el-button>
            </template>
          </el-alert>
          <el-empty
            v-else-if="screening.libraryDetail !== null && entryRows.length === 0"
            :description="t('screening.entriesEmpty')"
            :image-size="72"
          />
          <div v-else-if="entriesExpanded && screening.libraryDetail !== null" class="screening-table" :style="{ height: '320px' }">
            <el-auto-resizer>
              <template #default="{ width, height }">
                <el-table-v2
                  :columns="entryColumns"
                  :data="entryRows"
                  :width="width"
                  :height="height"
                  :row-height="36"
                  row-key="index"
                />
              </template>
            </el-auto-resizer>
          </div>
        </template>
      </div>
    </section>

    <!-- ② Config card -->
    <section v-if="hasRunSource && !activeRunning" class="vs-card">
      <div class="vs-card__header">
        <div class="vs-card__title">{{ t('screening.config') }}</div>
      </div>
      <div class="vs-card__body">
        <div v-if="!hasReceptor" class="prereqs">
          <div class="prereqs__item prereqs__item--missing">
            {{ t('docking.noReceptor') }}
          </div>
        </div>
        <div v-else class="form">
          <div class="form__field">
            <label class="form__label">{{ t('molecules.typeReceptor') }}</label>
            <MoleculeSelect kind="receptor" />
          </div>

          <div class="form__field">
            <label class="form__label">{{ t('docking.scoringFunction') }}</label>
            <ElSelect v-model="scoring" size="small" style="width: 100%">
              <ElOption
                v-for="opt in scoringOptions"
                :key="opt.value"
                :label="opt.label"
                :value="opt.value"
              />
            </ElSelect>
          </div>

          <div class="form__field">
            <label class="form__label">{{ t('docking.exhaustiveness') }}</label>
            <ElInputNumber
              v-model="exhaustiveness"
              :min="1"
              :max="512"
              size="small"
              style="width: 100%"
            />
          </div>

          <div class="form__field">
            <label class="form__label">{{ t('docking.numPoses') }}</label>
            <ElInputNumber v-model="nPoses" :min="1" :max="50" size="small" style="width: 100%" />
          </div>

          <div class="form__field">
            <label class="form__label">{{ t('docking.energyRange') }}</label>
            <ElInputNumber
              v-model="energyRange"
              :min="1"
              :max="10"
              :step="0.5"
              size="small"
              style="width: 100%"
            />
          </div>

          <div class="form__field">
            <label class="form__label">{{ t('docking.batch.parallelism') }}</label>
            <ElInputNumber
              v-model="parallelism"
              :min="1"
              :max="parallelismMax"
              :disabled="cpuCount === null"
              size="small"
              style="width: 100%"
            />
            <div class="form__hint">
              {{
                cpuCount === null
                  ? t('docking.batch.parallelismUnavailable')
                  : t('docking.batch.parallelismNote')
              }}
            </div>
          </div>

          <div class="screening-config__boxline">{{ boxLine }}</div>

          <div class="form__actions">
            <ElButton
              type="primary"
              :disabled="!canStart"
              :loading="starting"
              :title="startTitle"
              @click="startScreening"
            >
              {{ starting ? t('screening.starting') : t('screening.start') }}
            </ElButton>
          </div>
        </div>
      </div>
    </section>

    <!-- ③ Runs card -->
    <section class="vs-card">
      <div class="vs-card__header">
        <div class="vs-card__title">{{ t('screening.runs') }}</div>
      </div>
      <div class="vs-card__body" v-loading="screening.runsLoading">
        <el-alert
          v-if="screening.runsError"
          type="error"
          :closable="false"
          show-icon
          :title="t('screening.runsFailed')"
        >
          <template #default>
            <el-button size="small" :icon="Refresh" @click="screening.loadRuns()">
              {{ t('common.refresh') }}
            </el-button>
          </template>
        </el-alert>
        <el-empty
          v-else-if="screening.runs.length === 0"
          :description="t('screening.runEmpty')"
          :image-size="72"
        />
        <template v-else>
          <div v-if="screening.runStatus !== null" class="screening-runhead">
            <span
              class="status-badge"
              :class="`status-badge--${screening.runStatus.status}`"
            >
              {{ statusLabel(screening.runStatus.status) }}
            </span>
            <span class="screening-runcounts">
              {{ t('screening.runLib') }}: {{ screening.runStatus.libraryDisplayName || screening.runStatus.library }}
            </span>
            <span class="screening-runcounts">
              {{
                t('screening.counts', {
                  done: screening.runStatus.completedLigands,
                  total: screening.runStatus.totalLigands,
                  failed: screening.runStatus.failedLigands,
                })
              }}
            </span>
            <span
              class="screening-best"
              :class="
                screening.runStatus.bestAffinity !== null
                  ? 'screening-best--has'
                  : 'screening-best--none'
              "
            >
              {{ t('screening.colBest') }}:
              {{ screening.runStatus.bestAffinity !== null ? screening.runStatus.bestAffinity.toFixed(2) : '—' }}
            </span>
            <span v-if="screening.runStatus.currentLigand !== null" class="screening-runcounts">
              {{ t('screening.currentLigand', { name: screening.runStatus.currentLigand }) }}
            </span>
          </div>
          <ElProgress
            v-if="screening.runStatus !== null"
            :percentage="progressPercent(screening.runStatus.progress)"
          />
          <div
            v-if="
              screening.runStatus !== null &&
              (screening.runStatus.status === 'failed' ||
                screening.runStatus.status === 'cancelled')
            "
            class="screening-hint"
          >
            {{ t('screening.resumeHint') }}
          </div>
          <ElTable
            class="screening-runs-table"
            :data="screening.runs"
            size="small"
            @row-click="(row) => onRunRowClick(row.jobId)"
          >
            <ElTableColumn :label="t('screening.runLib')" min-width="120" show-overflow-tooltip>
              <template #default="{ row }">
                {{ row.libraryDisplayName || row.library }}
              </template>
            </ElTableColumn>
            <ElTableColumn :label="t('docking.batch.tableStatus')" width="110">
              <template #default="{ row }">
                <span class="status-badge" :class="`status-badge--${row.status}`">
                  {{ statusLabel(row.status) }}
                </span>
              </template>
            </ElTableColumn>
            <ElTableColumn :label="t('screening.colProgress')" width="90" align="right">
              <template #default="{ row }">{{ progressPercent(row.progress) }}%</template>
            </ElTableColumn>
            <ElTableColumn :label="t('screening.colBest')" width="100" align="right">
              <template #default="{ row }">
                <span
                  class="screening-best"
                  :class="row.bestAffinity !== null ? 'screening-best--has' : 'screening-best--none'"
                >
                  {{ row.bestAffinity !== null ? row.bestAffinity.toFixed(2) : '—' }}
                </span>
              </template>
            </ElTableColumn>
            <ElTableColumn :label="t('screening.viewRun')" width="160">
              <template #default="{ row }">
                <el-button text size="small" @click.stop="onRunRowClick(row.jobId)">
                  {{ t('screening.viewRun') }}
                </el-button>
                <el-button
                  v-if="row.status === 'failed' || row.status === 'cancelled'"
                  text
                  size="small"
                  @click.stop="onResume(row.jobId)"
                >
                  {{ t('screening.resume') }}
                </el-button>
                <el-button
                  v-if="row.status === 'running'"
                  text
                  size="small"
                  @click.stop="onCancelRun(row.jobId)"
                >
                  {{ t('screening.cancel') }}
                </el-button>
              </template>
            </ElTableColumn>
          </ElTable>
        </template>
      </div>
    </section>

    <!-- ④ Ranking card -->
    <section class="vs-card">
      <div class="vs-card__header">
        <div class="vs-card__title">{{ t('screening.ranking') }}</div>
      </div>
      <div class="vs-card__body" v-loading="screening.rankingLoading">
        <el-alert
          v-if="screening.rankingError"
          type="error"
          :closable="false"
          show-icon
          :title="t('screening.rankingFailed')"
        >
          <template #default>
            <el-button size="small" :icon="Refresh" @click="screening.loadRanking()">
              {{ t('common.refresh') }}
            </el-button>
          </template>
        </el-alert>
        <template v-else>
          <div class="screening-rankbar">
            <ElSelect
              :model-value="screening.rankingSortBy"
              size="small"
              style="width: 132px"
              @change="onSortChange"
            >
              <ElOption
                v-for="opt in sortOptions"
                :key="opt.value"
                :label="t(opt.labelKey)"
                :value="opt.value"
              />
            </ElSelect>
            <ElSelect
              :model-value="screening.rankingTop"
              size="small"
              style="width: 96px"
              @change="onTopChange"
            >
              <ElOption v-for="opt in topOptions" :key="opt" :label="String(opt)" :value="opt" />
            </ElSelect>
            <ElInput
              v-model="nameFilter"
              :placeholder="t('screening.filterPlaceholder')"
              size="small"
              clearable
            />
            <ElButton
              size="small"
              :icon="Download"
              :disabled="screening.ranking.length === 0"
              @click="exportRanking"
            >
              {{ t('screening.exportCsv') }}
            </ElButton>
            <span class="screening-ranktotal">
              {{ t('screening.rankTotal', { n: screening.rankingTotal }) }}
            </span>
            <span class="screening-rankhint">{{ t('screening.compareHint') }}</span>
          </div>
          <el-empty
            v-if="screening.ranking.length === 0"
            :description="t('screening.rankingEmpty')"
            :image-size="72"
          />
          <div v-else class="screening-table" :style="{ height: '460px' }">
            <el-auto-resizer>
              <template #default="{ width, height }">
                <el-table-v2
                  :columns="rankColumns"
                  :data="rankRows"
                  :width="width"
                  :height="height"
                  :row-height="36"
                  row-key="rank"
                  :row-event-handlers="rankRowEvents"
                />
              </template>
            </el-auto-resizer>
          </div>
        </template>
      </div>
    </section>

    <ElDrawer v-model="detailOpen" :title="t('screening.detailTitle')" size="380px">
      <template v-if="detailRank">
        <p class="screening-detail-hint">{{ t('screening.detailHint') }}</p>
        <dl class="screening-detail">
          <dt>{{ t('screening.colName') }}</dt><dd>{{ detailRank.name }}</dd>
          <dt>{{ t('screening.colIndex') }}</dt><dd>{{ detailRank.ligandIndex }}</dd>
          <dt>{{ t('screening.colAffinity') }}</dt>
          <dd>{{ detailRank.affinity === null ? '—' : detailRank.affinity.toFixed(2) }} kcal/mol</dd>
          <dt>{{ t('screening.colPoses') }}</dt><dd>{{ detailRank.nPoses ?? '—' }}</dd>
          <dt>{{ t('screening.colQed') }}</dt><dd>{{ detailRank.qed === null ? '—' : detailRank.qed.toFixed(3) }}</dd>
          <dt>{{ t('screening.colLipinski') }}</dt><dd>{{ detailRank.lipinskiViolations ?? '—' }}</dd>
          <dt>{{ t('screening.detailElapsed') }}</dt>
          <dd>{{ detailRank.elapsedMs == null ? '—' : (detailRank.elapsedMs / 1000).toFixed(2) + ' s' }}</dd>
          <dt>SMILES</dt><dd class="break">{{ detailRank.smiles || '—' }}</dd>
          <dt>{{ t('screening.detailOutDir') }}</dt><dd class="break"><code>{{ detailRank.outDir || '—' }}</code></dd>
        </dl>
      </template>
    </ElDrawer>

    <CatalogSelectionDialog v-model="selectionOpen" kind="ligand" @selected="onSelectionPicked" />

    <ScreeningImportDialog v-model="importOpen" @imported="onImported" />
  </div>
</template>

<style scoped>
/* Config fields: copied rules (each view holds its own, batch precedent). */
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

.form__hint {
  font-size: 11px;
  color: var(--vs-text-faint);
  line-height: 1.4;
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

/* Library bar */
.screening-libbar {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
  width: 100%;
}

.screening-libbar .el-select {
  flex: 1 1 220px;
  min-width: 200px;
}

.screening-preview { display: flex; flex-wrap: wrap; gap: 4px 10px; margin: 4px 0 8px; font-size: 11px; color: var(--vs-text-faint); }
.screening-preview span { border: 1px solid var(--vs-border); border-radius: 999px; padding: 1px 6px; }
.screening-libmeta {
  font-size: 12px;
  color: var(--vs-text-faint);
  margin: 8px 0;
}

.screening-config__boxline {
  font-family: var(--vs-font-mono);
  font-size: 12px;
  color: var(--vs-text-muted);
  margin-bottom: 8px;
}

/* Run card */
.screening-runhead {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
  margin-bottom: 8px;
}

.screening-runcounts {
  font-size: 12px;
  color: var(--vs-text-muted);
}

.screening-best {
  font-family: var(--vs-font-mono);
  font-size: 12px;
}

.screening-best--has {
  color: var(--vs-accent);
}

.screening-best--none {
  color: var(--vs-text-faint);
}

.screening-hint {
  font-size: 11px;
  color: var(--vs-text-faint);
  line-height: 1.4;
  margin: 6px 0;
}

.screening-runs-table {
  margin-top: 8px;
  cursor: pointer;
}

/* Status badges: ResultsSearchView three states + running accent (§5). */
.status-badge {
  display: inline-block;
  font-family: var(--vs-font-mono);
  font-size: 11px;
  border-radius: var(--vs-radius-sm);
  padding: 1px 6px;
  white-space: nowrap;
}

.status-badge--running {
  color: var(--vs-accent);
  background: color-mix(in srgb, var(--vs-accent) 14%, transparent);
}

.status-badge--completed {
  color: var(--vs-success);
  background: color-mix(in srgb, var(--vs-success) 14%, transparent);
}

.status-badge--failed {
  color: var(--vs-danger);
  background: color-mix(in srgb, var(--vs-danger) 14%, transparent);
}

.status-badge--cancelled {
  color: var(--vs-text-faint);
  background: color-mix(in srgb, var(--vs-text-faint) 14%, transparent);
}

/* Ranking toolbar */
.screening-rankbar {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
  margin-bottom: 8px;
}

.screening-rankbar .el-input {
  flex: 1 1 180px;
}

.screening-ranktotal {
  font-size: 11px;
  color: var(--vs-text-faint);
}

.screening-rankhint {
  font-size: 11px;
  color: var(--vs-warning);
  margin-left: auto;
}

/* Virtual table containers: three states live outside the table body. */
.screening-table {
  border: 1px solid var(--vs-border);
  border-radius: var(--vs-radius);
  overflow: hidden;
}

.screening-table :deep(.scr-num) {
  font-family: var(--vs-font-mono);
  font-size: 12px;
}

.screening-table :deep(.scr-num--has) {
  color: var(--vs-accent);
}

.screening-table :deep(.scr-num--none) {
  color: var(--vs-text-faint);
}

.screening-table :deep(.scr-lip--pass) {
  color: var(--vs-success);
  font-family: var(--vs-font-mono);
  font-size: 12px;
}

.screening-table :deep(.scr-lip--warn) {
  color: var(--vs-warning);
  font-family: var(--vs-font-mono);
  font-size: 12px;
}

.screening-table :deep(.scr-lip--danger) {
  color: var(--vs-danger);
  font-family: var(--vs-font-mono);
  font-size: 12px;
}

.screening-table :deep(.scr-prep--done) {
  color: var(--vs-success);
}

.screening-table :deep(.scr-prep--failed) {
  color: var(--vs-danger);
}

.screening-table :deep(.scr-prep--none) {
  color: var(--vs-text-faint);
}
.screening-detail-hint { margin: 0 0 10px; font-size: 12px; color: var(--vs-text-muted); }
.screening-detail { display: grid; grid-template-columns: 112px 1fr; gap: 6px 10px; font-size: 12px; }
.screening-detail dt { color: var(--vs-text-muted); }
.screening-detail dd { margin: 0; word-break: break-word; }
.screening-selection { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; font-size: 12px; color: var(--vs-text-muted); }
</style>
