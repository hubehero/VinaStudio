<script setup lang="ts">
import { Download, Search, TopRight } from '@element-plus/icons-vue'
import {
  ElAlert,
  ElButton,
  ElEmpty,
  ElInput,
  ElMessage,
  ElOption,
  ElSelect,
  ElTable,
  ElTableColumn,
  ElTag,
} from 'element-plus'
import { onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { openInBrowser } from '@/api/bridge'
import { api } from '@/api/http'
import { useMoleculeStore } from '@/stores/molecules'
import type {
  CompoundHit,
  CompoundSearchMode,
  CompoundSourceId,
  CompoundSourceInfo,
} from '@/types/api'

const { t } = useI18n()
const store = useMoleculeStore()
const props = withDefaults(defineProps<{ catalogMode?: boolean }>(), { catalogMode: false })
const emit = defineEmits<{ fetched: [path: string] }>()

const source = ref<CompoundSourceId>('pubchem')
const mode = ref<CompoundSearchMode>('text')
const query = ref('')
const threshold = ref(85)
const limit = 25
const results = ref<CompoundHit[]>([])
const total = ref(0)
const selected = ref<CompoundHit | null>(null)
const loading = ref(false)
const loadingMore = ref(false)
const fetching = ref<string | null>(null)
const error = ref<string | null>(null)
const warnings = ref<string[]>([])
const sources = ref<CompoundSourceInfo[]>([])
let generation = 0

const sourceOptions: { value: CompoundSourceId; label: string }[] = [
  { value: 'pubchem', label: 'PubChem' },
  { value: 'chembl', label: 'ChEMBL' },
]
const modeOptions: { value: CompoundSearchMode; label: string }[] = [
  { value: 'text', label: t('library.modeText') },
  { value: 'similarity', label: t('library.modeSimilarity') },
  { value: 'substructure', label: t('library.modeSubstructure') },
]

onMounted(async () => {
  try {
    sources.value = await api.compoundSources()
  } catch {
    // The static provider list remains usable if /sources is unavailable.
  }
})

watch([source, mode], () => {
  results.value = []
  total.value = 0
  selected.value = null
  warnings.value = []
  clearError()
})

function clearError(): void {
  error.value = null
}

async function runSearch(reset: boolean): Promise<void> {
  const text = query.value.trim()
  if (!text || (reset && loading.value) || (!reset && loadingMore.value)) return
  if (reset) {
    generation += 1
    results.value = []
    total.value = 0
    selected.value = null
    warnings.value = []
    loading.value = true
  } else {
    loadingMore.value = true
  }
  const requestGeneration = generation
  clearError()
  try {
    const page = await api.compoundSearch({
      source: source.value,
      mode: mode.value,
      query: text,
      limit,
      offset: reset ? 0 : results.value.length,
      threshold: threshold.value,
    })
    if (requestGeneration !== generation) return
    results.value = reset ? page.results : [...results.value, ...page.results]
    total.value = page.total
    warnings.value = page.warnings
    if (reset && page.results.length > 0) selected.value = page.results[0] ?? null
  } catch (cause) {
    if (requestGeneration !== generation) return
    error.value = cause instanceof Error ? cause.message : String(cause)
  } finally {
    if (requestGeneration === generation) {
      loading.value = false
      loadingMore.value = false
    }
  }
}

function search(): void {
  void runSearch(true)
}

function loadMore(): void {
  void runSearch(false)
}

function handleKeydown(event: Event): void {
  if ((event as KeyboardEvent).key === 'Enter') search()
}

function selectHit(hit: CompoundHit): void {
  selected.value = hit
}

async function fetchHit(hit: CompoundHit): Promise<void> {
  if (fetching.value) return
  fetching.value = `${hit.source}:${hit.id}`
  try {
    const result = await api.compoundFetch({ source: hit.source, id: hit.id })
    if (props.catalogMode) {
      emit('fetched', result.path)
    } else {
      await store.loadFromLibrary(result.path, result.name, result.bytes, 'ligand')
    }
    ElMessage.success(
      result.has3D
        ? t('library.compoundFetched', { name: result.name })
        : t('library.compoundFetchedNeedsPrepare', { name: result.name }),
    )
  } catch (cause) {
    ElMessage.error(
      `${t('library.fetchFailed')}: ${cause instanceof Error ? cause.message : String(cause)}`,
    )
  } finally {
    fetching.value = null
  }
}

async function openSource(hit: CompoundHit): Promise<void> {
  await openInBrowser(hit.sourceUrl)
}

function imageUrl(hit: CompoundHit): string {
  return hit.source === 'chembl'
    ? `https://www.ebi.ac.uk/chembl/api/data/image/${encodeURIComponent(hit.id)}?dimensions=320`
    : `https://pubchem.ncbi.nlm.nih.gov/image/imgsrv.fcgi?cid=${encodeURIComponent(hit.id)}&t=l`
}

function propertyValue(hit: CompoundHit, key: string): string {
  const aliases: Record<string, string> = {
    hbd: 'HBondDonorCount',
    hba: 'HBondAcceptorCount',
    psa: 'TPSA',
  }
  const value = hit.properties[aliases[key] ?? key] ?? hit.properties[key]
  return value === undefined || value === null || value === '' ? '—' : String(value)
}
</script>

<template>
  <div class="compound-tab">
    <div class="compound-toolbar">
      <ElSelect v-model="source" size="small" style="width: 120px">
        <ElOption
          v-for="option in sourceOptions"
          :key="option.value"
          :label="option.label"
          :value="option.value"
        />
      </ElSelect>
      <ElSelect v-model="mode" size="small" style="width: 132px">
        <ElOption
          v-for="option in modeOptions"
          :key="option.value"
          :label="option.label"
          :value="option.value"
        />
      </ElSelect>
      <ElInput
        v-model="query"
        :placeholder="t('library.compoundPlaceholder')"
        clearable
        size="small"
        :prefix-icon="Search"
        @keydown="handleKeydown"
      >
        <template #append>
          <ElButton :icon="Search" :loading="loading" @click="search">
            {{ t('library.search') }}
          </ElButton>
        </template>
      </ElInput>
      <div v-if="mode !== 'text'" class="threshold">
        <span>{{ t('library.threshold') }}</span>
        <ElSelect v-model="threshold" size="small" style="width: 76px">
          <ElOption :value="70" label="70" />
          <ElOption :value="80" label="80" />
          <ElOption :value="85" label="85" />
          <ElOption :value="90" label="90" />
        </ElSelect>
      </div>
    </div>

    <p class="compound-help">
      {{ sources.find((item) => item.id === source)?.note || t('library.compoundHelp') }}
    </p>
    <ElAlert
      v-for="warning in warnings"
      :key="warning"
      :title="warning"
      type="warning"
      :closable="false"
      show-icon
    />
    <ElAlert v-if="error" :title="error" type="error" :closable="false" show-icon />
    <p v-if="total > 0" class="compound-count">
      {{ t('library.resultCount', { n: total }) }}
      <span v-if="results.length < total"> · {{ t('library.showing', { n: results.length }) }}</span>
    </p>

    <div v-if="results.length > 0" class="compound-layout">
      <div class="compound-results">
        <ElTable
          :data="results"
          size="small"
          max-height="380"
          row-key="id"
          highlight-current-row
          :current-row-key="selected ? `${selected.source}:${selected.id}` : undefined"
          @row-click="selectHit"
        >
          <ElTableColumn :label="t('library.compoundSource')" width="82">
            <template #default="{ row }">
              <ElTag size="small" type="info" disable-transitions>{{ row.source }}</ElTag>
            </template>
          </ElTableColumn>
          <ElTableColumn prop="id" :label="t('library.compoundId')" width="120" />
          <ElTableColumn prop="name" :label="t('library.name')" min-width="150" show-overflow-tooltip />
          <ElTableColumn prop="formula" :label="t('library.formula')" width="110" />
          <ElTableColumn :label="t('library.mwShort')" width="82" align="right">
            <template #default="{ row }">
              {{ row.molecularWeight === null ? '—' : row.molecularWeight.toFixed(1) }}
            </template>
          </ElTableColumn>
          <ElTableColumn :label="t('library.threeD')" width="60" align="center">
            <template #default="{ row }">
              {{ row.has3D ? '✓' : '—' }}
            </template>
          </ElTableColumn>
        </ElTable>
        <div v-if="results.length < total" class="compound-more">
          <ElButton size="small" :loading="loadingMore" @click="loadMore">
            {{ t('library.loadMore') }}
          </ElButton>
        </div>
      </div>

      <div v-if="selected" class="compound-detail">
        <img class="compound-detail__image" :src="imageUrl(selected)" :alt="selected.name" />
        <div class="compound-detail__body">
          <div class="compound-detail__head">
            <div>
              <div class="compound-detail__name">{{ selected.name }}</div>
              <div class="compound-detail__id mono">{{ selected.source }} · {{ selected.id }}</div>
            </div>
            <ElButton
              type="primary"
              size="small"
              :icon="Download"
              :loading="fetching === `${selected.source}:${selected.id}`"
              @click="fetchHit(selected)"
            >
              {{ t('library.downloadLigand') }}
            </ElButton>
          </div>
          <dl class="compound-detail__meta">
            <div><dt>{{ t('library.formula') }}</dt><dd>{{ selected.formula || '—' }}</dd></div>
            <div><dt>{{ t('library.mwShort') }}</dt><dd>{{ selected.molecularWeight?.toFixed(1) || '—' }}</dd></div>
            <div><dt>{{ t('library.threeD') }}</dt><dd>{{ selected.has3D ? t('library.threeDYes') : t('library.threeDNo') }}</dd></div>
            <div><dt>HBD / HBA</dt><dd>{{ propertyValue(selected, 'hbd') }} / {{ propertyValue(selected, 'hba') }}</dd></div>
            <div><dt>TPSA</dt><dd>{{ propertyValue(selected, 'psa') }}</dd></div>
          </dl>
          <div v-if="selected.smiles" class="compound-detail__smiles mono">{{ selected.smiles }}</div>
          <p class="compound-detail__license">{{ selected.license }}</p>
          <ElButton text size="small" :icon="TopRight" @click="openSource(selected)">
            {{ t('library.openSource') }}
          </ElButton>
        </div>
      </div>
    </div>

    <ElEmpty v-else-if="!loading && query.trim()" :description="t('library.noResults')" />
  </div>
</template>

<style scoped>
.compound-tab {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 420px;
}

.compound-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.compound-toolbar .el-input {
  flex: 1;
  min-width: 240px;
}

.threshold {
  display: flex;
  align-items: center;
  gap: 4px;
  color: var(--vs-text-muted);
  font-size: 12px;
}

.compound-help,
.compound-count {
  margin: 0;
  color: var(--vs-text-faint);
  font-size: 11.5px;
}

.compound-layout {
  display: flex;
  gap: 12px;
  min-height: 360px;
}

.compound-results {
  flex: 1 1 58%;
  min-width: 0;
}

.compound-more {
  display: flex;
  justify-content: center;
  padding: 8px 0;
}

.compound-detail {
  flex: 1 1 42%;
  min-width: 0;
  border: 1px solid var(--vs-border);
  border-radius: var(--vs-radius);
  padding: 10px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  overflow: auto;
}

.compound-detail__image {
  width: 100%;
  max-height: 150px;
  object-fit: contain;
  background: #fff;
  border-radius: var(--vs-radius-sm);
}

.compound-detail__head {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: flex-start;
}

.compound-detail__name {
  font-size: 14px;
  font-weight: 600;
}

.compound-detail__id,
.mono {
  font-family: var(--vs-font-mono);
  font-size: 11.5px;
  color: var(--vs-text-muted);
}

.compound-detail__meta {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 4px 8px;
  margin: 0;
  font-size: 12px;
}

.compound-detail__meta div {
  display: flex;
  justify-content: space-between;
  gap: 6px;
}

.compound-detail__meta dt {
  color: var(--vs-text-faint);
}

.compound-detail__meta dd {
  margin: 0;
}

.compound-detail__smiles {
  word-break: break-all;
  background: var(--vs-bg-sunken);
  border-radius: var(--vs-radius-sm);
  padding: 6px;
}

.compound-detail__license {
  margin: 0;
  color: var(--vs-text-faint);
  font-size: 11px;
  line-height: 1.4;
}
</style>
