<script setup lang="ts">
import { Download, Search, WarningFilled } from '@element-plus/icons-vue'
import {
  ElButton,
  ElDialog,
  ElEmpty,
  ElInput,
  ElMessage,
  ElTable,
  ElTableColumn,
  ElTag,
} from 'element-plus'
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { api } from '@/api/http'
import { useMoleculeStore } from '@/stores/molecules'
import type { LibraryEntry, LibraryLigand } from '@/types/api'

const { t } = useI18n()
const store = useMoleculeStore()

const visible = ref(false)
const query = ref('')
const searching = ref(false)
const entries = ref<LibraryEntry[]>([])
const totalCount = ref(0)
const fetchedId = ref<string | null>(null)

/** Selected entry for detail panel. */
const selected = ref<LibraryEntry | null>(null)
const loadingDetail = ref(false)

/** 3D preview state. */
const previewContainer = ref<HTMLElement | null>(null)
let previewViewer: import('3dmol').GLViewer | null = null
const previewLoading = ref(false)

function open(): void {
  visible.value = true
  entries.value = []
  totalCount.value = 0
  query.value = ''
  selected.value = null
}

async function doSearch(): Promise<void> {
  const q = query.value.trim()
  if (!q) return
  searching.value = true
  selected.value = null
  try {
    const result = await api.librarySearch({ query: q, rows: 30 })
    entries.value = result.entries
    totalCount.value = result.totalCount
  } catch (error) {
    ElMessage.error(
      `${t('library.searchFailed')}: ${error instanceof Error ? error.message : String(error)}`,
    )
  } finally {
    searching.value = false
  }
}

function handleSearchKeydown(e: Event): void {
  if ((e as KeyboardEvent).key === 'Enter') {
    void doSearch()
  }
}

async function selectEntry(entry: LibraryEntry): Promise<void> {
  // If already selected, do nothing
  if (selected.value?.pdbId === entry.pdbId) return

  selected.value = entry
  loadingDetail.value = true
  try {
    // Fetch full detail (authors, chains, etc.)
    const detail = await api.libraryEntry(entry.pdbId)
    selected.value = detail
    // Load 3D preview
    void loadPreview(detail.pdbId)
  } catch {
    // Keep the basic entry data from search results
    void loadPreview(entry.pdbId)
  } finally {
    loadingDetail.value = false
  }
}

async function loadPreview(pdbId: string): Promise<void> {
  previewLoading.value = true
  try {
    const $3Dmol = await import('3dmol')
    await nextTick()

    if (!previewContainer.value) return

    // Dispose previous viewer
    if (previewViewer) {
      previewViewer.removeAllModels()
      previewViewer = null
    }

    const viewer = $3Dmol.createViewer(previewContainer.value, {
      backgroundColor: '#0d1526',
      antialias: true,
      cartoonQuality: 8,
    })
    previewViewer = viewer

    // Fetch CIF from RCSB (inline URL, CORS-friendly)
    const cifUrl = `https://files.rcsb.org/view/${pdbId}.cif`
    const resp = await fetch(cifUrl)
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    const cifData = await resp.text()

    viewer.addModel(cifData, 'cif')
    viewer.setStyle({}, { cartoon: { colorscheme: 'spectrum' } })

    // Highlight ligands as sticks
    viewer.setStyle({ hetflag: true }, {
      stick: { radius: 0.16, colorscheme: 'Jmol' },
      sphere: { scale: 0.3, colorscheme: 'Jmol' },
    })

    viewer.zoomTo()
    viewer.render()
  } catch (err) {
    console.warn('[library] 3D preview failed:', err)
  } finally {
    previewLoading.value = false
  }
}

// Clean up viewer when dialog closes
watch(visible, (v) => {
  if (!v) {
    previewViewer?.removeAllModels()
    previewViewer = null
  }
})

onBeforeUnmount(() => {
  previewViewer?.removeAllModels()
  previewViewer = null
})

// -- Download actions --------------------------------------------------------

const fetchingAll = ref(false)

async function fetchAll(entry: LibraryEntry): Promise<void> {
  fetchingAll.value = true
  try {
    const ligandIds = entry.ligands.map((l) => l.id)
    const result = await api.libraryFetchAll({ pdbId: entry.pdbId, ligandIds })
    await store.loadFromLibraryGroup(
      result.receptor,
      result.ligands.map((l) => ({ path: l.path, name: l.name, bytes: l.bytes })),
      entry.pdbId,
    )
    ElMessage.success(t('library.fetchedAll', { id: entry.pdbId }))
    visible.value = false
  } catch (error) {
    ElMessage.error(
      `${t('library.fetchFailed')}: ${error instanceof Error ? error.message : String(error)}`,
    )
  } finally {
    fetchingAll.value = false
  }
}

async function fetchReceptor(entry: LibraryEntry): Promise<void> {
  fetchedId.value = entry.pdbId
  try {
    const result = await api.libraryFetch({ pdbId: entry.pdbId, kind: 'receptor' })
    await store.loadFromLibrary(result.path, result.name, result.bytes, 'receptor')
    ElMessage.success(t('library.fetched', { id: entry.pdbId }))
    visible.value = false
  } catch (error) {
    ElMessage.error(
      `${t('library.fetchFailed')}: ${error instanceof Error ? error.message : String(error)}`,
    )
  } finally {
    fetchedId.value = null
  }
}

async function fetchLigand(entry: LibraryEntry, ligand: LibraryLigand): Promise<void> {
  fetchedId.value = `${entry.pdbId}-${ligand.id}`
  try {
    const result = await api.libraryFetch({
      pdbId: entry.pdbId,
      kind: 'ligand',
      ligandId: ligand.id,
    })
    await store.loadFromLibrary(result.path, result.name, result.bytes, 'ligand')
    ElMessage.success(t('library.fetchedLigand', { id: ligand.id }))
    visible.value = false
  } catch (error) {
    ElMessage.error(
      `${t('library.fetchFailed')}: ${error instanceof Error ? error.message : String(error)}`,
    )
  } finally {
    fetchedId.value = null
  }
}

function isFetching(pdbId: string, ligandId?: string): boolean {
  if (!fetchedId.value) return false
  if (ligandId) return fetchedId.value === `${pdbId}-${ligandId}`
  return fetchedId.value === pdbId
}

function formatResolution(r: number | null): string {
  if (r === null || r === undefined) return '—'
  return `${r.toFixed(2)} Å`
}

function formatWeight(w: number | null): string {
  if (w === null || w === undefined) return '—'
  return w >= 1000 ? `${(w / 1000).toFixed(1)} kDa` : `${w.toFixed(0)} Da`
}

defineExpose({ open })
</script>

<template>
  <ElDialog
    v-model="visible"
    :title="t('library.title')"
    width="900px"
    :close-on-click-modal="false"
    destroy-on-close
  >
    <div class="library">
      <!-- Left: search + results -->
      <div class="library__left">
        <ElInput
          v-model="query"
          :placeholder="t('library.placeholder')"
          clearable
          :prefix-icon="Search"
          @keydown="handleSearchKeydown"
        >
          <template #append>
            <ElButton :icon="Search" :loading="searching" @click="doSearch">
              {{ t('library.search') }}
            </ElButton>
          </template>
        </ElInput>

        <p v-if="totalCount > 0" class="library__count">
          {{ t('library.resultCount', { n: totalCount }) }}
        </p>

        <div v-if="entries.length > 0" class="library__results">
          <ElTable
            :data="entries"
            stripe
            size="small"
            max-height="420"
            row-key="pdbId"
            highlight-current-row
            :current-row-key="selected?.pdbId"
            @row-click="selectEntry"
          >
            <ElTableColumn prop="pdbId" :label="t('library.pdbId')" width="75">
              <template #default="{ row }">
                <span class="mono">{{ row.pdbId }}</span>
              </template>
            </ElTableColumn>
            <ElTableColumn prop="title" :label="t('library.title_')" min-width="180" show-overflow-tooltip />
            <ElTableColumn :label="t('library.method')" width="90" show-overflow-tooltip>
              <template #default="{ row }">
                <ElTag v-if="row.method" size="small" type="info" disable-transitions>
                  {{ row.method.replace('X-RAY DIFFRACTION', 'X-ray').replace('ELECTRON MICROSCOPY', 'EM') }}
                </ElTag>
              </template>
            </ElTableColumn>
            <ElTableColumn :label="t('library.resolution')" width="70" align="right">
              <template #default="{ row }">
                <span class="mono">{{ formatResolution(row.resolution) }}</span>
              </template>
            </ElTableColumn>
          </ElTable>
        </div>

        <ElEmpty
          v-else-if="!searching && query.trim().length > 0"
          :description="t('library.noResults')"
        />
      </div>

      <!-- Right: detail + preview -->
      <div v-if="selected" class="library__right">
        <div class="detail">
          <div class="detail__header">
            <span class="detail__pdbid mono">{{ selected.pdbId }}</span>
            <div class="detail__actions">
              <ElButton
                size="small"
                :icon="Download"
                :loading="isFetching(selected.pdbId)"
                @click="fetchReceptor(selected)"
              >
                {{ t('library.downloadReceptor') }}
              </ElButton>
              <ElButton
                type="primary"
                size="small"
                :icon="Download"
                :loading="fetchingAll"
                @click="fetchAll(selected)"
              >
                {{ t('library.downloadAll') }}
              </ElButton>
            </div>
          </div>

          <h4 class="detail__title">{{ selected.title }}</h4>

          <!-- Warning for non-protein structures -->
          <div v-if="selected.moleculeType !== 'protein' && selected.moleculeType !== 'unknown'" class="detail__warning">
            <el-icon><WarningFilled /></el-icon>
            <span v-if="selected.moleculeType === 'rna'">{{ t('library.warningRNA') }}</span>
            <span v-else-if="selected.moleculeType === 'dna'">{{ t('library.warningDNA') }}</span>
            <span v-else-if="selected.moleculeType === 'hybrid'">{{ t('library.warningHybrid') }}</span>
          </div>

          <div class="detail__meta">
            <div v-if="selected.method" class="detail__row">
              <span class="detail__label">{{ t('library.method') }}</span>
              <span>{{ selected.method }}</span>
            </div>
            <div v-if="selected.resolution !== null" class="detail__row">
              <span class="detail__label">{{ t('library.resolution') }}</span>
              <span class="mono">{{ formatResolution(selected.resolution) }}</span>
            </div>
            <div v-if="selected.year" class="detail__row">
              <span class="detail__label">{{ t('library.year') }}</span>
              <span>{{ selected.year }}</span>
            </div>
            <div v-if="selected.journal" class="detail__row">
              <span class="detail__label">{{ t('library.journal') }}</span>
              <span>{{ selected.journal }}</span>
            </div>
            <div v-if="selected.organism" class="detail__row">
              <span class="detail__label">{{ t('library.organism') }}</span>
              <span>{{ selected.organism }}</span>
            </div>
            <div v-if="selected.atomCount" class="detail__row">
              <span class="detail__label">{{ t('library.atoms') }}</span>
              <span class="mono">{{ selected.atomCount.toLocaleString() }}</span>
            </div>
            <div v-if="selected.molecularWeight" class="detail__row">
              <span class="detail__label">{{ t('library.mw') }}</span>
              <span>{{ formatWeight(selected.molecularWeight) }}</span>
            </div>
          </div>

          <!-- Chains -->
          <div v-if="selected.chains.length > 0" class="detail__section">
            <h5 class="detail__section-title">{{ t('library.chains') }}</h5>
            <div v-for="chain in selected.chains" :key="chain.entityId" class="chain-item">
              <span class="chain-item__desc">{{ chain.description || t('library.polymer') }}</span>
              <span v-if="chain.organism" class="chain-item__org">{{ chain.organism }}</span>
              <span v-if="chain.sequenceLength" class="chain-item__len mono">
                {{ chain.sequenceLength }} {{ t('library.residues') }}
              </span>
            </div>
          </div>

          <!-- Ligands -->
          <div v-if="selected.ligands.length > 0" class="detail__section">
            <h5 class="detail__section-title">{{ t('library.ligands') }}</h5>
            <div v-for="lig in selected.ligands" :key="lig.id" class="ligand-item">
              <div class="ligand-item__info">
                <span class="ligand-item__id mono">{{ lig.id }}</span>
                <span class="ligand-item__name">{{ lig.name }}</span>
                <span v-if="lig.formula" class="ligand-item__formula mono">{{ lig.formula }}</span>
                <span v-if="lig.molecularWeight" class="ligand-item__mw">
                  {{ formatWeight(lig.molecularWeight) }}
                </span>
              </div>
              <ElButton
                size="small"
                :icon="Download"
                :loading="isFetching(selected.pdbId, lig.id)"
                @click="fetchLigand(selected, lig)"
              >
                {{ t('library.downloadLigand') }}
              </ElButton>
            </div>
          </div>

          <!-- Authors -->
          <div v-if="selected.authors.length > 0" class="detail__section">
            <h5 class="detail__section-title">{{ t('library.authors') }}</h5>
            <p class="detail__authors">{{ selected.authors.join(', ') }}</p>
          </div>
        </div>

        <!-- 3D Preview -->
        <div class="preview">
          <div class="preview__header">
            <span>{{ t('library.preview') }}</span>
          </div>
          <div ref="previewContainer" class="preview__viewer">
            <div v-if="previewLoading" class="preview__loading">
              {{ t('library.previewLoading') }}
            </div>
          </div>
        </div>
      </div>

      <div v-else class="library__right library__right--empty">
        <ElEmpty :description="t('library.selectEntry')" :image-size="60" />
      </div>
    </div>

    <template #footer>
      <ElButton @click="visible = false">{{ t('common.done') }}</ElButton>
    </template>
  </ElDialog>
</template>

<style scoped>
.library {
  display: flex;
  gap: 16px;
  min-height: 420px;
}

.library__left {
  flex: 0 0 420px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.library__count {
  margin: 0;
  font-size: 12px;
  color: var(--vs-text-faint);
}

.library__results {
  border: 1px solid var(--vs-border);
  border-radius: var(--vs-radius);
  overflow: hidden;
}

.library__right {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
  border: 1px solid var(--vs-border);
  border-radius: var(--vs-radius);
  padding: 12px;
  overflow-y: auto;
  max-height: 480px;
}

.library__right--empty {
  align-items: center;
  justify-content: center;
}

.mono {
  font-family: var(--vs-font-mono);
}

/* -- Detail panel --------------------------------------------------------- */

.detail__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.detail__pdbid {
  font-size: 18px;
  font-weight: 700;
}

.detail__actions {
  display: flex;
  gap: 6px;
}

.detail__title {
  margin: 2px 0 8px;
  font-size: 13px;
  font-weight: 500;
  color: var(--vs-text);
  line-height: 1.4;
}

.detail__meta {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.detail__row {
  display: flex;
  gap: 8px;
  font-size: 12px;
}

.detail__label {
  min-width: 70px;
  color: var(--vs-text-faint);
  flex-shrink: 0;
}

.detail__section {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--vs-border);
}

.detail__section-title {
  margin: 0 0 6px;
  font-size: 12px;
  font-weight: 600;
  color: var(--vs-text);
}

.detail__authors {
  margin: 0;
  font-size: 11px;
  color: var(--vs-text-faint);
  line-height: 1.5;
}

.detail__warning {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  margin-bottom: 8px;
  border-radius: var(--vs-radius-sm);
  background: color-mix(in srgb, var(--vs-warning, #e6a817) 12%, transparent);
  border: 1px solid color-mix(in srgb, var(--vs-warning, #e6a817) 30%, transparent);
  font-size: 12px;
  color: var(--vs-warning, #b8860b);
  line-height: 1.4;
}

.chain-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 3px 0;
  font-size: 12px;
}

.chain-item__desc {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chain-item__org {
  color: var(--vs-text-faint);
  font-size: 11px;
}

.chain-item__len {
  color: var(--vs-text-faint);
  font-size: 11px;
}

.ligand-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 4px 0;
}

.ligand-item__info {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 0;
}

.ligand-item__id {
  font-weight: 600;
  min-width: 32px;
}

.ligand-item__name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
}

.ligand-item__formula {
  font-size: 11px;
  color: var(--vs-text-faint);
}

.ligand-item__mw {
  font-size: 11px;
  color: var(--vs-text-faint);
}

/* -- 3D Preview ----------------------------------------------------------- */

.preview {
  margin-top: 4px;
  border-top: 1px solid var(--vs-border);
  padding-top: 8px;
}

.preview__header {
  font-size: 12px;
  font-weight: 600;
  color: var(--vs-text);
  margin-bottom: 6px;
}

.preview__viewer {
  width: 100%;
  height: 240px;
  border-radius: var(--vs-radius);
  overflow: hidden;
  background: #0d1526;
  position: relative;
}

.preview__loading {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--vs-text-faint);
  font-size: 12px;
}
</style>
