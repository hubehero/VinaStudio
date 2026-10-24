<script setup lang="ts">
import { onMounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import { useDockingStore } from '@/stores/docking'
import type { DockingJobSummary } from '@/types/api'

const { t } = useI18n()
const router = useRouter()
const docking = useDockingStore()

onMounted(() => {
  void docking.fetchJobs()
})

// A job that finishes while this view is open must appear in the list.
watch(
  () => docking.status,
  (s) => {
    if (s === 'completed' || s === 'failed' || s === 'cancelled') {
      void docking.fetchJobs()
    }
  },
)

function rowLabel(job: DockingJobSummary): string {
  if (job.isBatch) return t('docking.history.batch')
  return job.label || t('docking.history.untitled')
}

function formatTime(epochSeconds: number): string {
  if (!epochSeconds) return '—'
  const d = new Date(epochSeconds * 1000)
  const pad = (n: number): string => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function formatBest(job: DockingJobSummary): string {
  return job.bestAffinity === null ? '—' : job.bestAffinity.toFixed(2)
}

function bestHint(job: DockingJobSummary): string {
  if (job.bestAffinity === null) return ''
  if (job.bestAffinity === 0) return t('docking.history.zeroScoreHint')
  if (job.bestAffinity > 0) return t('docking.history.positiveScoreHint')
  return ''
}

function bestClass(job: DockingJobSummary): Record<string, boolean> {
  return { 'history__best--warn': job.bestAffinity !== null && job.bestAffinity >= 0 }
}

async function open(job: DockingJobSummary): Promise<void> {
  if (job.isBatch) {
    await docking.openHistoryBatch(job)
    await router.push('/batch')
    return
  }
  await docking.openHistoryJob(job)
}
</script>

<template>
  <div class="vs-card">
    <div class="vs-card__header">
      <div>
        <div class="vs-card__title">{{ t('docking.history.title') }}</div>
      </div>
    </div>
    <div class="vs-card__body">
      <p v-if="docking.jobSummaries.length === 0" class="history__empty">
        {{ t('docking.history.empty') }}
      </p>
      <template v-else>
        <div class="history__head" aria-hidden="true">
          <span>{{ t('docking.history.colTime') }}</span>
          <span>{{ t('docking.history.colLigand') }}</span>
          <span class="history__best">{{ t('docking.history.colBest') }}</span>
          <span>{{ t('docking.history.colStatus') }}</span>
        </div>
        <ul class="history__list">
          <li v-for="job in docking.jobSummaries" :key="job.jobId">
            <button
              type="button"
              class="history__row"
              :class="{ 'history__row--active': job.jobId === docking.activeJobId }"
              :title="`${rowLabel(job)} · ${formatBest(job)} kcal/mol`"
              :aria-label="`${formatTime(job.createdAt)} ${rowLabel(job)} ${t(`docking.status.${job.status}`)}`"
              @click="open(job)"
            >
              <span class="history__time">{{ formatTime(job.createdAt) }}</span>
              <span class="history__label">{{ rowLabel(job) }}</span>
              <span class="history__best" :class="bestClass(job)" :title="bestHint(job)">
                {{ formatBest(job) }}
              </span>
              <span class="history__badge" :class="`history__badge--${job.status}`">
                {{ t(`docking.status.${job.status}`) }}
              </span>
            </button>
          </li>
        </ul>
      </template>
    </div>
  </div>
</template>

<style scoped>
.history__empty {
  font-size: 12.5px;
  color: var(--vs-text-faint);
  margin: 0;
}

.history__head,
.history__row {
  display: grid;
  grid-template-columns: 100px minmax(0, 1fr) 52px 68px;
  gap: 6px;
  align-items: center;
}

.history__head span {
  white-space: nowrap;
}

.history__head {
  font-size: 11px;
  font-weight: 600;
  color: var(--vs-text-faint);
  padding: 0 8px 6px;
}

.history__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 220px;
  overflow-y: auto;
}

.history__row {
  width: 100%;
  padding: 6px 8px;
  border: 1px solid transparent;
  border-radius: var(--vs-radius);
  background: transparent;
  font: inherit;
  font-size: 12.5px;
  color: var(--vs-text);
  text-align: left;
  cursor: pointer;
}

.history__row:hover {
  background: var(--vs-bg-sunken);
}

.history__row:focus-visible {
  outline: 2px solid var(--vs-accent);
  outline-offset: 1px;
}

.history__row--active {
  border-color: var(--vs-accent);
}

.history__time {
  color: var(--vs-text-muted);
  font-variant-numeric: tabular-nums;
}

.history__label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.history__best {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.history__best--warn {
  color: var(--vs-warning);
  cursor: help;
}

.history__badge {
  justify-self: start;
  padding: 1px 8px;
  border-radius: 999px;
  font-size: 11px;
  line-height: 1.6;
}

.history__badge--completed {
  background: rgba(103, 194, 58, 0.15);
  color: #67c23a;
}

.history__badge--failed {
  background: rgba(245, 108, 108, 0.15);
  color: #f56c6c;
}

.history__badge--cancelled {
  background: rgba(144, 147, 153, 0.15);
  color: #909399;
}

.history__badge--running,
.history__badge--queued {
  background: rgba(64, 158, 255, 0.15);
  color: var(--vs-accent);
}
</style>
