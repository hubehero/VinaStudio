<script setup lang="ts">
import { Document, Position, Refresh } from '@element-plus/icons-vue'
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import DockingReport from '@/components/docking/DockingReport.vue'
import JobHistory from '@/components/docking/JobHistory.vue'
import MethodsDialog from '@/components/docking/MethodsDialog.vue'
import { useDockingStore } from '@/stores/docking'

const { t } = useI18n()
const router = useRouter()
const docking = useDockingStore()
const methodsOpen = ref(false)

onMounted(async () => {
  // Land on an actual report rather than the empty state: history is this
  // page's material, so the newest finished single-job run opens by default.
  // An already-active job wins — a run started elsewhere must never be
  // hijacked (openHistoryJob resets the store before loading the new job).
  await docking.fetchJobs()
  if (docking.activeJobId) return
  const latest = docking.jobSummaries.find((job) => !job.isBatch && job.status === 'completed')
  if (latest) void docking.openHistoryJob(latest)
})

function refresh(): void {
  void docking.fetchJobs()
  // Idempotent: re-pulls status and reloads the result when the active job
  // finished while this page was open without polling (restored jobs).
  void docking.refreshStatus()
}

function inspectInDock(): void {
  // Reports are read-only; pose browsing and 3D interaction analysis live on
  // the docking view, against whatever job is active here.
  if (docking.activeJobId) void router.push('/docking')
}
</script>

<template>
  <div class="vs-page report-view">
    <div class="vs-page__head">
      <div>
        <h1 class="vs-page__title">{{ t('docking.resultsReport.title') }}</h1>
        <p class="vs-page__subtitle">{{ t('docking.resultsReport.subtitle') }}</p>
      </div>
      <div class="report-view__actions">
        <el-button
          :icon="Document"
          :disabled="!docking.hasResult"
          @click="methodsOpen = true"
        >
          {{ t('docking.methods.button') }}
        </el-button>
        <el-button
          :icon="Position"
          :disabled="!docking.activeJobId"
          @click="inspectInDock"
        >
          {{ t('docking.resultsReport.openInDock') }}
        </el-button>
        <el-button :icon="Refresh" @click="refresh">{{ t('common.refresh') }}</el-button>
      </div>
    </div>

    <!-- Report takes the wide column; the history picker picks which run the
         report is about. Below 1180px they stack, report first. -->
    <div class="report-view__grid">
      <DockingReport class="report-view__report" />
      <JobHistory class="report-view__history" />
    </div>

    <MethodsDialog v-model="methodsOpen" />
  </div>
</template>

<style scoped>
.report-view__grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(300px, 340px);
  gap: 16px;
  align-items: start;
}

.report-view__actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

/* The card is tuned for the 380px docking sidebar: on this wide column its
   meta rows and stat tiles should spread out instead of leaving a void in
   the middle of space-between rows. */
.report-view__report :deep(.report-meta) {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 4px 28px;
}

.report-view__report :deep(.report-stats) {
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
}

@media (max-width: 1180px) {
  .report-view__grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
