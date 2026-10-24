<script setup lang="ts">
import { DataAnalysis, Download } from '@element-plus/icons-vue'
import { ElAlert, ElButton, ElIcon, ElMessage, ElProgress } from 'element-plus'
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { saveTextFile } from '@/api/bridge'
import { api } from '@/api/http'
import HelpLink from '@/components/HelpLink.vue'
import StatusPill from '@/components/StatusPill.vue'
import DockingCharts from '@/components/docking/analysis/DockingCharts.vue'
import IfpSection from '@/components/docking/IfpSection.vue'
import type { PoseFindingSeverity } from '@/types/api'
import { useDockingStore } from '@/stores/docking'

const { t, te } = useI18n()
const docking = useDockingStore()

// -- header / meta -----------------------------------------------------------

const statusLabel = computed(() => {
  const s = docking.status
  if (s === 'queued' || s === 'running' || s === 'completed' || s === 'failed' || s === 'cancelled') {
    return t(`docking.status.${s}`)
  }
  return ''
})

/** StatusPill tone for the job state; idle shows no pill at all. */
const scoreWarning = computed<string | null>(() => {
  const score = docking.bestAffinity
  if (score === null) return null
  if (score === 0) return t('docking.resultsReport.zeroScore')
  if (score > 0) return t('docking.resultsReport.positiveScore')
  return null
})

const statusTone = computed<'ok' | 'warn' | 'error' | 'idle'>(() => {
  switch (docking.status) {
    case 'completed':
      return 'ok'
    case 'failed':
      return 'error'
    case 'cancelled':
      return 'warn'
    default:
      return 'idle'
  }
})

/** History row for the active job — carries createdAt and label fallbacks. */
const activeSummary = computed(() =>
  docking.jobSummaries.find((s) => s.jobId === docking.activeJobId) ?? null,
)

const jobLabel = computed(
  () => docking.activeJobLabel || activeSummary.value?.label || '—',
)

function formatTime(epochSeconds: number | undefined): string {
  if (!epochSeconds) return '—'
  const d = new Date(epochSeconds * 1000)
  const pad = (n: number): string => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function formatElapsed(ms: number | null): string {
  if (ms === null) return '—'
  const s = Math.floor(ms / 1000)
  const m = Math.floor(s / 60)
  const sec = s % 60
  return m > 0 ? `${m}m ${sec}s` : `${sec}s`
}

const createdAtText = computed(() => formatTime(activeSummary.value?.createdAt))

const scoringText = computed(() => {
  const scoring = docking.jobResult?.scoring ?? activeSummary.value?.scoring
  if (scoring === 'ad4') return 'AutoDock4'
  if (scoring === 'vinardo') return 'Vinardo'
  if (scoring === 'vina') return 'Vina'
  return '—'
})

const elapsedText = computed(() => formatElapsed(docking.elapsedMs))

// -- metrics -----------------------------------------------------------------

const validationCounts = computed(() => {
  const result = docking.validation
  if (!result) return null
  const counts = { ok: 0, warning: 0, error: 0 }
  for (const pose of result.poses) {
    if (pose.worstSeverity === 'error') counts.error += 1
    else if (pose.worstSeverity === 'warning') counts.warning += 1
    else counts.ok += 1
  }
  return counts
})

const rmsdRateText = computed(() => {
  const result = docking.rmsd
  if (!result) return null
  return `${Math.round(result.successRate * 100)}%`
})

// -- ranked poses ------------------------------------------------------------

/** ✓ / ⚠ / ✗ glyph for a pose's worst severity (null before validation). */
function statusGlyph(poseIndex: number): string {
  const item = docking.validation?.poses.find((p) => p.poseIndex === poseIndex)
  if (!item) return ''
  if (item.worstSeverity === 'error') return '✗'
  if (item.worstSeverity === 'warning') return '⚠'
  return '✓'
}

function statusClass(poseIndex: number): string {
  const item = docking.validation?.poses.find((p) => p.poseIndex === poseIndex)
  if (!item) return ''
  if (item.worstSeverity === 'error') return 'status--error'
  if (item.worstSeverity === 'warning') return 'status--warning'
  return 'status--ok'
}

/** C1/C2/… badge for a pose (1-based index), or '' before clustering. */
function clusterBadge(poseIndex: number): string {
  const result = docking.clusters
  if (!result) return ''
  const ordinal = result.clusters.findIndex((c) => c.members.includes(poseIndex - 1))
  return ordinal >= 0 ? `C${ordinal + 1}` : ''
}

// -- validation findings aggregation -----------------------------------------

interface FindingRow {
  key: string
  code: string
  severity: PoseFindingSeverity
  count: number
}

/**
 * Collapse every pose's findings into one list per message, worst severity
 * first — the card summarises the run, not the currently selected pose.
 */
const findingsSummary = computed<FindingRow[]>(() => {
  const result = docking.validation
  if (!result) return []
  const byKey = new Map<string, FindingRow>()
  for (const pose of result.poses) {
    for (const finding of pose.findings) {
      const prev = byKey.get(finding.messageKey)
      if (prev) {
        prev.count += 1
        if (finding.severity === 'error') prev.severity = 'error'
      } else {
        byKey.set(finding.messageKey, {
          key: finding.messageKey,
          code: finding.code,
          severity: finding.severity,
          count: 1,
        })
      }
    }
  }
  return [...byKey.values()].sort((a, b) => {
    if (a.severity !== b.severity) return a.severity === 'error' ? -1 : 1
    return b.count - a.count
  })
})

/** Resolve a finding's messageKey to a locale string; fall back to the code. */
function findingMessage(row: FindingRow): string {
  if (te(row.key)) return t(row.key)
  return row.code
}

// -- clusters / log ----------------------------------------------------------

const clusterRows = computed(() =>
  (docking.clusters?.clusters ?? []).map((cluster, index) => ({
    ordinal: index + 1,
    size: cluster.size,
  })),
)

const logExcerpt = computed(() => docking.logLines.slice(-8))

// -- figure caption (TASK-47-C) ---------------------------------------------
// The caption is deliberately explicit about what the figure is not: the
// numbers are scoring-function estimates, overlays are colours only, and no
// electrostatic potential is drawn.
const appVersion = ref('')

onMounted(async () => {
  try {
    appVersion.value = (await api.systemInfo()).app.version
  } catch {
    // Keep the caption usable; the version is not a scientific result.
  }
})

function paramText(key: string): string {
  const value = docking.jobResult?.params?.[key]
  if (value === undefined || value === null || value === '') return '—'
  return String(value)
}

function vectorText(key: string): string {
  const value = docking.jobResult?.params?.[key]
  if (!Array.isArray(value) || value.length !== 3) return '—'
  return value.map((item) => Number(item).toFixed(3)).join(', ')
}

const figureCaption = computed(() =>
  t('docking.figureCaption.text', {
    label: jobLabel.value,
    version: appVersion.value || '—',
    scoring: scoringText.value,
    exhaustiveness: paramText('exhaustiveness'),
    seed: paramText('seed'),
    center: vectorText('center'),
    size: vectorText('size'),
    poses: docking.poses.length,
    best: docking.bestAffinity === null ? '—' : docking.bestAffinity.toFixed(2),
  }),
)

async function copyCaption(): Promise<void> {
  try {
    await navigator.clipboard.writeText(figureCaption.value)
    ElMessage.success(t('docking.figureCaption.copied'))
  } catch {
    ElMessage.error(t('docking.figureCaption.failed'))
  }
}

// -- actions -----------------------------------------------------------------

async function downloadCsv(): Promise<void> {
  if (!docking.activeJobId) return
  try {
    const result = await api.exportCsv(
      docking.activeJobId,
      docking.rmsdReferencePath ?? undefined,
    )
    // False only means "desktop dialog cancelled or write failed" — the host
    // reports write errors itself, so there is nothing to toast here.
    await saveTextFile(result.csv, {
      filename: result.filename,
      mime: 'text/csv',
      saveTitle: t('docking.saveFile.title'),
    })
  } catch {
    // Reuse the results-card copy; the endpoint and payload are identical.
    ElMessage.error(t('docking.errorExportCsv'))
  }
}
</script>

<template>
  <div class="vs-card report">
    <div class="vs-card__header">
      <div>
        <div class="vs-card__title">{{ t('docking.resultsReport.title') }}</div>
        <div class="vs-card__subtitle">{{ t('docking.resultsReport.subtitle') }}</div>
      </div>
      <StatusPill
        v-if="docking.status !== 'idle'"
        :state="statusTone"
        :label="statusLabel"
        :pulse="docking.isRunning"
      />
    </div>

    <div class="vs-card__body report__body">
      <div v-if="docking.status === 'failed'" class="report__help">
        <HelpLink topic="dockingFailed" />
      </div>
      <!-- Empty: nothing run yet. -->
      <div v-if="!docking.hasResult && !docking.isRunning" class="report__empty">
        <ElIcon :size="26"><DataAnalysis /></ElIcon>
        <p class="report__empty-title">{{ t('docking.resultsReport.empty') }}</p>
        <p class="report__empty-hint">{{ t('docking.resultsReport.emptyHint') }}</p>
      </div>

      <template v-else>
        <!-- Job meta -->
        <dl class="report-meta">
          <div class="report-meta__row">
            <dt>{{ t('docking.resultsReport.metaLigand') }}</dt>
            <dd class="vs-mono">{{ jobLabel }}</dd>
          </div>
          <div class="report-meta__row">
            <dt>{{ t('docking.resultsReport.metaCreated') }}</dt>
            <dd>{{ createdAtText }}</dd>
          </div>
          <div class="report-meta__row">
            <dt>{{ t('docking.resultsReport.metaScoring') }}</dt>
            <dd>{{ scoringText }}</dd>
          </div>
          <div class="report-meta__row">
            <dt>{{ t('docking.resultsReport.metaElapsed') }}</dt>
            <dd>{{ elapsedText }}</dd>
          </div>
        </dl>

        <!-- Running progress -->
        <div v-if="docking.isRunning" class="report-running">
          <ElProgress
            :percentage="docking.progress"
            :indeterminate="docking.isRunning"
            :show-text="false"
            :stroke-width="8"
          />
          <span v-if="docking.stage" class="report-running__stage">
            {{ t(`docking.stage.${docking.stage}`) }}
          </span>
          <span class="report-running__hint">{{ t('docking.progressHint') }}</span>
        </div>

        <ElAlert
          v-if="scoreWarning"
          :title="scoreWarning"
          type="warning"
          :closable="false"
          show-icon
          class="report-score-warning"
        />

        <!-- Key metrics -->
        <section v-if="docking.hasResult" class="report-section">
          <h4 class="report-section__title">
            {{ t('docking.resultsReport.metricsTitle') }}
          </h4>
          <div class="report-stats">
            <div class="report-stat report-stat--accent">
              <span class="report-stat__label">
                {{ t('docking.resultsReport.metricBest') }}
              </span>
              <span class="report-stat__value">
                {{ docking.bestAffinity !== null ? docking.bestAffinity.toFixed(2) : '—' }}
                <small>{{ t('docking.resultsReport.unitKcal') }}</small>
              </span>
            </div>
            <div class="report-stat">
              <span class="report-stat__label">
                {{ t('docking.resultsReport.metricPoses') }}
              </span>
              <span class="report-stat__value">{{ docking.poses.length }}</span>
            </div>
            <div v-if="validationCounts" class="report-stat">
              <span class="report-stat__label">
                {{ t('docking.resultsReport.metricValidation') }}
              </span>
              <span class="report-stat__value">
                {{ validationCounts.ok }}/{{ validationCounts.ok + validationCounts.warning + validationCounts.error }}
              </span>
            </div>
            <div v-if="rmsdRateText" class="report-stat">
              <span class="report-stat__label">
                {{ t('docking.resultsReport.metricRmsd') }}
              </span>
              <span class="report-stat__value">{{ rmsdRateText }}</span>
            </div>
            <div v-if="docking.clusters" class="report-stat">
              <span class="report-stat__label">
                {{ t('docking.resultsReport.metricClusters') }}
              </span>
              <span class="report-stat__value">{{ docking.clusters.nClusters }}</span>
            </div>
          </div>
        </section>

        <!-- Ranked poses: collapsed by default so the report scans top-down,
             with the count and a chevron advertising the hidden list. Native
             <details> mirrors the log-excerpt disclosure below; no new state. -->
        <details v-if="docking.poses.length > 0" class="report-section report-disclosure">
          <summary class="report-disclosure__summary">
            <span class="report-section__title">
              {{ t('docking.resultsReport.posesTitle') }}
            </span>
            <span class="report-disclosure__count">{{ docking.poses.length }}</span>
          </summary>
          <p class="report-hint">{{ t('docking.resultsReport.posesHint') }}</p>
          <ol class="report-poses">
            <li
              v-for="pose in docking.poses"
              :key="pose.index"
              class="report-poses__row"
              :class="{
                'is-active': pose.index === docking.currentPose?.index,
                'is-best': docking.bestAffinity !== null && pose.affinity === docking.bestAffinity,
              }"
              @click="docking.selectPose(pose.index - 1)"
            >
              <span class="report-poses__idx">#{{ pose.index }}</span>
              <span class="report-poses__aff">{{ pose.affinity.toFixed(2) }}</span>
              <span class="report-poses__rmsd">
                {{ pose.rmsdLower.toFixed(2) }}–{{ pose.rmsdUpper.toFixed(2) }}
              </span>
              <span v-if="clusterBadge(pose.index)" class="cluster-badge">
                {{ clusterBadge(pose.index) }}
              </span>
              <span
                v-if="docking.validation"
                class="report-poses__status"
                :class="statusClass(pose.index)"
              >
                {{ statusGlyph(pose.index) }}
              </span>
            </li>
          </ol>
        </details>

        <!-- Analysis figures: affinity profile / distribution / funnel / RMSD -->
        <DockingCharts v-if="docking.hasResult && docking.poses.length > 0" />

        <!-- Validation summary -->
        <section v-if="docking.validation && validationCounts" class="report-section">
          <h4 class="report-section__title">
            {{ t('docking.resultsReport.validationTitle') }}
          </h4>
          <div class="report-counts">
            <span class="status--ok">✓ {{ t('docking.resultsReport.validationOk') }} {{ validationCounts.ok }}</span>
            <span class="status--warning">⚠ {{ t('docking.resultsReport.validationWarning') }} {{ validationCounts.warning }}</span>
            <span class="status--error">✗ {{ t('docking.resultsReport.validationError') }} {{ validationCounts.error }}</span>
          </div>
          <ul v-if="findingsSummary.length > 0" class="report-findings">
            <li
              v-for="row in findingsSummary"
              :key="row.key"
              :class="row.severity === 'error' ? 'status--error' : 'status--warning'"
            >
              <span class="report-findings__glyph">{{ row.severity === 'error' ? '✗' : '⚠' }}</span>
              <span class="report-findings__text">{{ findingMessage(row) }}</span>
              <span class="report-findings__count">×{{ row.count }}</span>
            </li>
          </ul>
        </section>

        <!-- RMSD vs reference -->
        <section v-if="docking.rmsd" class="report-section">
          <h4 class="report-section__title">
            {{ t('docking.resultsReport.rmsdTitle') }}
          </h4>
          <div class="report-line">
            <span>{{ t('docking.resultsReport.rmsdThreshold', { value: docking.rmsd.threshold }) }}</span>
            <span>{{ t('docking.resultsReport.rmsdRate', { rate: Math.round(docking.rmsd.successRate * 100) }) }}</span>
          </div>
        </section>

        <!-- Cluster summary -->
        <section v-if="docking.clusters" class="report-section">
          <h4 class="report-section__title">
            {{ t('docking.resultsReport.clustersTitle') }}
          </h4>
          <div class="report-chips">
            <span
              v-for="row in clusterRows"
              :key="row.ordinal"
              class="cluster-badge cluster-badge--rep"
            >
              C{{ row.ordinal }} · {{ t('docking.resultsReport.clusterMembers', { n: row.size }) }}
            </span>
          </div>
        </section>

        <!-- Interaction fingerprints (TASK-16) -->
        <IfpSection v-if="docking.hasResult && docking.poses.length > 0" />

        <!-- Log excerpt -->
        <details v-if="logExcerpt.length > 0" class="report-log">
          <summary>{{ t('docking.resultsReport.logTitle') }}</summary>
          <pre>{{ logExcerpt.join('\n') }}</pre>
        </details>

        <section class="report-section report-caption">
          <h4 class="report-section__title">{{ t('docking.figureCaption.title') }}</h4>
          <p class="report-caption__text">{{ figureCaption }}</p>
          <ElButton size="small" @click="copyCaption">
            {{ t('docking.figureCaption.copy') }}
          </ElButton>
        </section>

        <!-- Footer action -->
        <ElButton
          size="small"
          :icon="Download"
          :disabled="!docking.activeJobId || !docking.hasResult"
          @click="downloadCsv"
        >
          {{ t('docking.exportCsv') }}
        </ElButton>
      </template>
    </div>
  </div>
</template>

<style scoped>
.report__body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.report__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 18px 12px;
  text-align: center;
  color: var(--vs-text-faint);
}

.report__empty-title {
  margin: 0;
  font-size: 13px;
  color: var(--vs-text-muted);
}

.report__empty-hint {
  margin: 0;
  font-size: 11.5px;
  line-height: 1.5;
}

/* -- meta -- */

.report-meta {
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.report-meta__row {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  font-size: 12px;
}

.report-meta__row dt {
  color: var(--vs-text-faint);
}

.report-meta__row dd {
  margin: 0;
  color: var(--vs-text);
  text-align: right;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.report-running {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.report-running__stage {
  font-size: 11.5px;
  color: var(--vs-text-muted);
}

.report-running__hint {
  font-size: 11px;
  line-height: 1.4;
  color: var(--vs-text-faint);
}

.report-score-warning {
  margin: 2px 0;
}

/* -- sections -- */

.report-section {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.report-section__title {
  margin: 0;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--vs-text-faint);
}

.report-hint {
  margin: 0;
  font-size: 11px;
  color: var(--vs-text-faint);
}

/* -- stat tiles (2-col; mirrors the batch results-stat idiom) -- */

.report-stats {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px 12px;
}

.report-stat {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.report-stat__label {
  font-size: 11px;
  color: var(--vs-text-faint);
  text-transform: uppercase;
}

.report-stat__value {
  font-size: 18px;
  font-weight: 600;
  color: var(--vs-text);
  font-variant-numeric: tabular-nums;
}

.report-stat__value small {
  font-size: 11px;
  font-weight: 400;
  color: var(--vs-text-faint);
}

.report-stat--accent .report-stat__value {
  color: var(--vs-accent);
}

/* -- ranked pose rows -- */

.report-poses {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.report-poses__row {
  display: grid;
  grid-template-columns: 30px 54px minmax(0, 1fr) auto auto;
  gap: 6px;
  align-items: center;
  padding: 5px 6px;
  border-radius: var(--vs-radius-sm);
  font-size: 12.5px;
  font-variant-numeric: tabular-nums;
  cursor: pointer;
  color: var(--vs-text-muted);
}

.report-poses__row:hover {
  background: var(--vs-bg-sunken);
}

.report-poses__row.is-active {
  background: color-mix(in srgb, var(--vs-accent) 10%, transparent);
  color: var(--vs-text);
}

.report-poses__idx {
  font-family: var(--vs-font-mono);
  font-size: 11.5px;
  color: var(--vs-text-faint);
}

.report-poses__aff {
  font-weight: 600;
  color: var(--vs-text);
  text-align: right;
}

.report-poses__row.is-best .report-poses__aff {
  color: var(--vs-accent);
}

.report-poses__rmsd {
  text-align: right;
  color: var(--vs-text-faint);
}

.report-poses__status {
  text-align: center;
  width: 16px;
}

/* -- validation counts / findings -- */

.report-counts {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}

.report-findings {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.report-findings li {
  display: grid;
  grid-template-columns: 16px minmax(0, 1fr) auto;
  gap: 6px;
  align-items: start;
  font-size: 12px;
  line-height: 1.45;
}

.report-findings__glyph {
  text-align: center;
}

.report-findings__text {
  min-width: 0;
  word-break: break-word;
}

.report-findings__count {
  font-variant-numeric: tabular-nums;
  color: var(--vs-text-faint);
}

/* Severity colours — copied from DockingResults (scoped there, so the report
   keeps its own minimal copies rather than editing that card). */
.status--ok {
  color: var(--vs-success);
}

.status--warning {
  color: var(--vs-warning);
}

.status--error {
  color: var(--vs-danger);
}

.cluster-badge {
  display: inline-block;
  padding: 1px 6px;
  border-radius: 999px;
  background: var(--vs-bg-sunken);
  border: 1px solid var(--vs-border);
  font-family: var(--vs-font-mono);
  font-size: 10.5px;
  color: var(--vs-text-muted);
  white-space: nowrap;
}

.cluster-badge--rep {
  border-color: color-mix(in srgb, var(--vs-accent) 45%, transparent);
  color: var(--vs-accent);
}

/* -- misc lines -- */

.report-line {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  font-size: 12px;
  color: var(--vs-text-muted);
  font-variant-numeric: tabular-nums;
}

.report-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

/* Ranked-pose disclosure — default-closed; the marker rotates on open. */
.report-disclosure > summary {
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  list-style: none;
}

.report-disclosure > summary::-webkit-details-marker {
  display: none;
}

.report-disclosure > summary::before {
  content: '▸';
  font-size: 10px;
  line-height: 1;
  color: var(--vs-text-faint);
  transition: transform 0.15s ease;
}

.report-disclosure[open] > summary::before {
  transform: rotate(90deg);
}

.report-disclosure__count {
  font-size: 11px;
  color: var(--vs-text-faint);
  font-variant-numeric: tabular-nums;
}

.report-log summary {
  cursor: pointer;
  font-size: 11.5px;
  color: var(--vs-text-muted);
}

.report-caption__text {
  margin: 6px 0 0;
  font-size: 12px;
  line-height: 1.65;
  color: var(--vs-text-muted);
  white-space: pre-wrap;
}

.report-log pre {
  margin: 6px 0 0;
  padding: 8px 10px;
  max-height: 140px;
  overflow: auto;
  background: var(--vs-bg-sunken);
  border-radius: var(--vs-radius);
  font-family: var(--vs-font-mono);
  font-size: 11px;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-all;
  color: var(--vs-text-muted);
}
</style>
