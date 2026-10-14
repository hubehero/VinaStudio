<template>
  <ElDialog
    v-model="open"
    :title="t('ifp.groupTitle')"
    width="min(960px, 92vw)"
    destroy-on-close
  >
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
    <div v-if="data" class="ifp-chips">
      <span v-for="(cluster, i) in data.clusters" :key="i" class="ifp-chip">
        F{{ i + 1 }} ×{{ cluster.size }}
      </span>
      <span v-if="capped" class="ifp-state">{{ t('ifp.groupCapNote') }}</span>
    </div>
    <p v-if="error" class="ifp-state ifp-state--error">
      {{ t('ifp.groupError') }}
      <ElButton size="small" text @click="run">{{ t('ifp.retry') }}</ElButton>
    </p>
    <p v-else-if="data && !hasAnyContact" class="ifp-state">{{ t('ifp.emptyNoContacts') }}</p>
    <template v-else-if="data">
      <div class="ifp-meta">
        <span class="ifp-meta__item">{{ t('ifp.metaIfp') }} <b>{{ data.nClusters }}</b></span>
        <span class="ifp-meta__item">{{ t('ifp.metaContacts') }} <b>{{ avgBits }}</b></span>
      </div>
      <IfpMatrix
        :rows="rows"
        mode="group"
        :residues="data.residues"
        :types="data.types"
        :loading="loading"
        :ligand-header="t('ifp.colLigand')"
      />
    </template>
  </ElDialog>
</template>

<script setup lang="ts">
/** Batch-ligand grouping dialog: assembles workspace paths, groups by IFP. */
import { ElButton, ElDialog, ElSlider } from 'element-plus'
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { api } from '@/api/http'
import IfpMatrix from '@/components/docking/IfpMatrix.vue'
import { useMoleculeStore } from '@/stores/molecules'
import type {
  BatchLigandResult,
  IfpGroupLigand,
  IfpGroupResponse,
  IfpMatrixRow,
} from '@/types/api'

const props = defineProps<{
  modelValue: boolean
  /** Batch job the ligand rows belong to; poses live under this job's dir. */
  jobId: string
  /** Result rows carrying outDir — BatchJobResult.results, not the progress feed. */
  rows: BatchLigandResult[]
}>()

const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()

const { t } = useI18n()
const molecules = useMoleculeStore()

const open = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit('update:modelValue', value),
})

const data = ref<IfpGroupResponse | null>(null)
const cutoff = ref(0.5)
const loading = ref(false)
const error = ref(false)
const capped = ref(false)
/** Monotonic id: a response from a superseded request is dropped, not shown. */
let seq = 0

function buildLigands(): IfpGroupLigand[] {
  const eligible = props.rows
    .filter((row) => row.status === 'completed' && row.outDir)
    .sort(
      (a, b) =>
        (a.bestAffinity ?? Number.POSITIVE_INFINITY) -
        (b.bestAffinity ?? Number.POSITIVE_INFINITY),
    )
  capped.value = eligible.length > 200
  return eligible.slice(0, 200).map((row) => ({
    label: row.label,
    pdbqtPath: `jobs/${props.jobId}/${row.outDir}/poses.pdbqt`,
  }))
}

async function run(): Promise<void> {
  const receptorPath = molecules.receptorPdbqtPath
  if (!receptorPath) return
  const ligands = buildLigands()
  if (ligands.length < 2) return
  const mySeq = ++seq
  loading.value = true
  error.value = false
  try {
    const response = await api.ifpCluster({
      receptorPath,
      ligands,
      cutoff: cutoff.value,
    })
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

// Reopening refetches: the batch rows or the cutoff may have moved on.
watch(open, (isOpen) => {
  if (isOpen) {
    seq += 1
    data.value = null
    error.value = false
    run()
  }
})

const hasAnyContact = computed(
  () => data.value?.ligands.some((row) => row.nContacts > 0) ?? false,
)

const rows = computed<IfpMatrixRow[]>(() => {
  const payload = data.value
  if (!payload) return []
  const list = payload.ligands.map((row) => ({
    index: row.index,
    label: row.label,
    fpCluster: row.cluster,
    rmsdCluster: null,
    pairs: row.pairs,
  }))
  list.sort((a, b) => a.fpCluster - b.fpCluster || a.index - b.index)
  return list
})

const avgBits = computed(() => {
  const ligands = data.value?.ligands
  if (!ligands || ligands.length === 0) return '0.0'
  const total = ligands.reduce((sum, row) => sum + row.nContacts, 0)
  return (total / ligands.length).toFixed(1)
})
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
.ifp-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
  align-items: center;
}
.ifp-chip {
  font-family: var(--vs-font-mono);
  font-size: 11px;
  padding: 1px 6px;
  border: 1px solid var(--vs-border);
  border-radius: var(--vs-radius-sm);
  color: var(--vs-text-muted);
  background: var(--vs-bg-sunken);
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
