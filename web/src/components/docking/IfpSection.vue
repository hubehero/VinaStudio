<template>
  <section class="report-section">
    <h4 class="report-section__title">{{ t('ifp.sectionTitle') }}</h4>
    <div class="ifp-toolbar">
      <span class="ifp-toolbar__label">{{ t('ifp.cutoffLabel') }}</span>
      <ElSlider
        v-model="cutoff"
        class="ifp-toolbar__slider"
        :min="0"
        :max="1"
        :step="0.05"
        @change="run"
      />
      <span class="ifp-toolbar__value">{{ cutoff.toFixed(2) }}</span>
      <ElButton size="small" :loading="loading" @click="run">{{ t('ifp.retry') }}</ElButton>
    </div>
    <p v-if="error" class="ifp-state ifp-state--error">
      {{ t('ifp.error') }}
      <ElButton size="small" text @click="run">{{ t('ifp.retry') }}</ElButton>
    </p>
    <p v-else-if="data && !hasAnyContact" class="ifp-state">{{ t('ifp.emptyNoContacts') }}</p>
    <template v-else-if="data">
      <div class="ifp-meta">
        <span class="ifp-meta__item">{{ t('ifp.metaIfp') }} <b>{{ data.nClusters }}</b></span>
        <span v-if="docking.clusters" class="ifp-meta__item">
          {{ t('ifp.metaRmsd') }} <b>{{ docking.clusters.nClusters }}</b>
        </span>
        <span class="ifp-meta__item">{{ t('ifp.metaContacts') }} <b>{{ avgBits }}</b></span>
        <span v-if="agreement !== null" class="ifp-meta__item">
          {{ t('ifp.metaAgree', { pct: agreement }) }}
        </span>
        <ElButton v-if="!docking.clusters" size="small" text type="primary" @click="runRmsd">
          {{ t('ifp.runRmsd') }}
        </ElButton>
        <span v-else-if="agreement === null" class="ifp-state">{{ t('ifp.needRmsd') }}</span>
      </div>
      <IfpMatrix
        :rows="rows"
        :residues="data.residues"
        :types="data.types"
        mode="job"
        :loading="loading"
        :pose-header="t('ifp.colPose')"
        :active-index="docking.currentPoseIndex"
        @select="onSelect"
      />
    </template>
  </section>
</template>

<script setup lang="ts">
/** Report section: fetch this job's interaction fingerprints and compare partitions. */
import { ElButton, ElSlider } from 'element-plus'
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { api } from '@/api/http'
import IfpMatrix from '@/components/docking/IfpMatrix.vue'
import { useDockingStore } from '@/stores/docking'
import type { IfpJobResponse, IfpMatrixRow } from '@/types/api'

const { t } = useI18n()
const docking = useDockingStore()

const data = ref<IfpJobResponse | null>(null)
const cutoff = ref(0.5)
const loading = ref(false)
const error = ref(false)
/** Monotonic id: a response from a superseded request is dropped, not shown. */
let seq = 0

async function run(): Promise<void> {
  const jobId = docking.activeJobId
  if (!jobId) return
  const mySeq = ++seq
  loading.value = true
  error.value = false
  try {
    const response = await api.jobIfp(jobId, { cutoff: cutoff.value })
    if (mySeq !== seq) return
    data.value = response
  } catch {
    if (mySeq !== seq) return
    data.value = null
    error.value = true
  } finally {
    if (mySeq === seq) loading.value = false
  }
}

// Mount = a finished job is on screen; a job switch refetches from scratch.
watch(
  () => docking.activeJobId,
  () => {
    seq += 1
    data.value = null
    error.value = false
    run()
  },
  { immediate: true },
)

const hasAnyContact = computed(() => data.value?.fingerprints.some((fp) => fp.nContacts > 0) ?? false)

/** Pose index → RMSD cluster ordinal, or null before RMSD clustering ran. */
const rmsdClusterOf = computed<Map<number, number> | null>(() => {
  const result = docking.clusters
  if (!result) return null
  const map = new Map<number, number>()
  result.clusters.forEach((cluster, ordinal) => {
    for (const member of cluster.members) map.set(member, ordinal)
  })
  return map
})

const rows = computed<IfpMatrixRow[]>(() => {
  const payload = data.value
  if (!payload) return []
  const fpOrdinal = new Map<number, number>()
  payload.clusters.forEach((cluster, ordinal) => {
    for (const member of cluster.members) fpOrdinal.set(member, ordinal)
  })
  const rmsd = rmsdClusterOf.value
  const list = payload.fingerprints.map((fp) => ({
    index: fp.index,
    label: String(fp.index + 1),
    fpCluster: fpOrdinal.get(fp.index) ?? 0,
    rmsdCluster: rmsd ? (rmsd.get(fp.index) ?? null) : null,
    pairs: fp.pairs,
  }))
  // Matrix rows read as cluster blocks, then pose order inside a block.
  list.sort((a, b) => a.fpCluster - b.fpCluster || a.index - b.index)
  return list
})

const avgBits = computed(() => {
  const fingerprints = data.value?.fingerprints
  if (!fingerprints || fingerprints.length === 0) return '0.0'
  const total = fingerprints.reduce((sum, fp) => sum + fp.nContacts, 0)
  return (total / fingerprints.length).toFixed(1)
})

/** Percent of pose pairs whose same/different verdict matches RMSD's; null = not comparable. */
const agreement = computed<number | null>(() => {
  const payload = data.value
  const rmsd = rmsdClusterOf.value
  if (!payload || !rmsd) return null
  const fpOrdinal = new Map<number, number>()
  payload.clusters.forEach((cluster, ordinal) => {
    for (const member of cluster.members) fpOrdinal.set(member, ordinal)
  })
  const n = payload.fingerprints.length
  let same = 0
  let total = 0
  for (let i = 0; i < n; i++) {
    for (let j = i + 1; j < n; j++) {
      total += 1
      if ((fpOrdinal.get(i) === fpOrdinal.get(j)) === (rmsd.get(i) === rmsd.get(j))) same += 1
    }
  }
  if (total === 0) return null
  return Math.round((same / total) * 100)
})

function onSelect(index: number): void {
  docking.selectPose(index)
}

function runRmsd(): void {
  // The store caches by jobId:cutoff, so a re-click with the slider unchanged is free.
  void docking.runCluster()
}
</script>

<style scoped>
.ifp-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}
.ifp-toolbar__label {
  font-size: 12px;
  color: var(--vs-text-muted);
  white-space: nowrap;
}
.ifp-toolbar__slider {
  flex: 1 1 auto;
  max-width: 220px;
}
.ifp-toolbar__value {
  font-family: var(--vs-font-mono);
  font-size: 12px;
  color: var(--vs-text-muted);
}
.ifp-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  align-items: center;
  margin-bottom: 8px;
  font-size: 12px;
  color: var(--vs-text-muted);
}
.ifp-meta__item b {
  font-family: var(--vs-font-mono);
  color: var(--vs-text);
}
.ifp-state {
  font-size: 12px;
  color: var(--vs-text-muted);
}
.ifp-state--error {
  color: var(--vs-danger);
}
</style>
