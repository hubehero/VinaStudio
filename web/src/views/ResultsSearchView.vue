<script setup lang="ts">
import { Search, Star, StarFilled } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { api } from '@/api/http'
import type { ResultRunDetail, ResultRunSummary, SavedView, TagCount } from '@/types/api'
import { useUndoStore } from '@/stores/undo'

const { t } = useI18n()
const undo = useUndoStore()

const PAGE_SIZE = 50

const query = ref('')
const rows = ref<ResultRunSummary[]>([])
const loaded = ref(false)
const loading = ref(false)
const loadingMore = ref(false)
const hasMore = ref(false)
const offset = ref(0)
const error = ref(false)
let requestId = 0
// 比较选择存摘要对象：跨搜索/过滤保留；顺序 = 勾选顺序；上限 4。
const selected = ref<ResultRunSummary[]>([])
const compareOpen = ref(false)
const compareLoading = ref(false)
const compareError = ref(false)
const compareRuns = ref<ResultRunDetail[]>([])

const favoritesOnly = ref(false)
const tagFilter = ref<string[]>([])
const tags = ref<TagCount[]>([])
const views = ref<SavedView[]>([])
const selectedView = ref<number | null>(null)
const saveViewOpen = ref(false)
const viewName = ref('')
const tagDialogOpen = ref(false)
const tagJob = ref<ResultRunSummary | null>(null)
const tagDraft = ref<string[]>([])
const tagInput = ref('')
const bulkTag = ref('')


async function search(): Promise<void> {
  const id = ++requestId
  loading.value = true
  loadingMore.value = false
  error.value = false
  try {
    const page = await api.resultsSearch(query.value.trim(), {
      limit: PAGE_SIZE,
      offset: 0,
      favorites: favoritesOnly.value,
      tags: tagFilter.value,
    })
    if (id !== requestId) return
    rows.value = page
    offset.value = page.length
    hasMore.value = page.length === PAGE_SIZE
    loaded.value = true
    await loadTags()
  } catch {
    if (id === requestId) error.value = true
  } finally {
    if (id === requestId) {
      loading.value = false
      loadingMore.value = false
    }
  }
}

async function loadMore(): Promise<void> {
  if (!hasMore.value || loading.value || loadingMore.value) return
  const id = ++requestId
  loadingMore.value = true
  try {
    const page = await api.resultsSearch(query.value.trim(), {
      limit: PAGE_SIZE,
      offset: offset.value,
      favorites: favoritesOnly.value,
      tags: tagFilter.value,
    })
    if (id !== requestId) return
    const known = new Set(rows.value.map((run) => run.jobId))
    rows.value = [...rows.value, ...page.filter((run) => !known.has(run.jobId))]
    offset.value += page.length
    hasMore.value = page.length === PAGE_SIZE
  } catch {
    if (id === requestId) ElMessage.error(t('results.loadMoreFailed'))
  } finally {
    if (id === requestId) {
      loading.value = false
      loadingMore.value = false
    }
  }
}

async function loadTags(): Promise<void> {
  try {
    tags.value = await api.resultsTags()
  } catch {
    // The table remains usable; tag filtering is an enhancement.
  }
}

async function loadViews(): Promise<void> {
  try {
    views.value = await api.resultsViews()
  } catch {
    views.value = []
  }
}

function isPicked(jobId: string): boolean {
  return selected.value.some((run) => run.jobId === jobId)
}

function toggle(row: ResultRunSummary): void {
  const index = selected.value.findIndex((run) => run.jobId === row.jobId)
  if (index >= 0) {
    selected.value.splice(index, 1)
    return
  }
  selected.value.push(row)
}

function rowClassName({ row }: { row: ResultRunSummary }): string {
  return isPicked(row.jobId) ? 'is-picked' : ''
}

function clearSelection(): void {
  selected.value = []
  compareOpen.value = false
  compareRuns.value = []
  compareError.value = false
}

async function openCompare(): Promise<void> {
  if (selected.value.length < 2) return
  compareOpen.value = true
  compareLoading.value = true
  compareError.value = false
  compareRuns.value = []
  try {
    compareRuns.value = await api.resultsCompare(selected.value.map((run) => run.jobId))
  } catch {
    compareError.value = true
  } finally {
    compareLoading.value = false
  }
}

// 时间格式复制自 JobHistory.vue（同为 epoch 秒语义；设计 §7 要求复制不 import）
function formatTime(epochSeconds: number): string {
  if (!epochSeconds) return '—'
  const d = new Date(epochSeconds * 1000)
  const pad = (n: number): string => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

// 形态复制自 BatchDockingView（null 走设计 §5 的缺值 —，不用其原样 '-'）
function formatElapsed(ms: number | null): string {
  if (ms === null) return '—'
  const s = Math.floor(ms / 1000)
  const m = Math.floor(s / 60)
  const sec = s % 60
  return m > 0 ? `${m}m ${sec}s` : `${sec}s`
}

function affinityText(run: ResultRunSummary): string {
  return run.bestAffinity === null ? '—' : run.bestAffinity.toFixed(2)
}

// 设计 §5：exhaustiveness 与 n_poses 任一缺失则整行省略。
function paramsText(run: ResultRunDetail): string | null {
  const exhaustiveness = run.params?.['exhaustiveness']
  const nPoses = run.params?.['n_poses']
  if (typeof exhaustiveness !== 'number' || typeof nPoses !== 'number') return null
  return `E=${exhaustiveness} N=${nPoses}`
}

async function toggleFavorite(row: ResultRunSummary): Promise<void> {
  try {
    const result = await api.resultsUpdateRun(row.jobId, { favorite: !row.favorite })
    row.favorite = result.favorite
    row.tags = result.tags
    if (favoritesOnly.value) await search()
  } catch {
    ElMessage.error(t('results.updateFailed'))
  }
}

function openTagEditor(row: ResultRunSummary): void {
  tagJob.value = row
  tagDraft.value = [...row.tags]
  tagInput.value = ''
  tagDialogOpen.value = true
}

function addTagDraft(): void {
  const tag = tagInput.value.trim()
  if (!tag) return
  if (!tagDraft.value.includes(tag)) tagDraft.value.push(tag)
  tagInput.value = ''
}

function removeTagDraft(tag: string): void {
  tagDraft.value = tagDraft.value.filter((item) => item !== tag)
}

async function saveTags(): Promise<void> {
  if (!tagJob.value) return
  try {
    const result = await api.resultsUpdateRun(tagJob.value.jobId, {
      tags: tagDraft.value,
    })
    tagJob.value.tags = result.tags
    tagJob.value.favorite = result.favorite
    tagDialogOpen.value = false
    await loadTags()
    await search()
  } catch {
    ElMessage.error(t('results.updateFailed'))
  }
}

async function bulkFavorite(favorite: boolean): Promise<void> {
  if (selected.value.length === 0) return
  try {
    await api.resultsBulkUpdate({
      runIds: selected.value.map((run) => run.jobId),
      favorite,
    })
    clearSelection()
    await search()
  } catch {
    ElMessage.error(t('results.updateFailed'))
  }
}

async function bulkAddTag(): Promise<void> {
  const tag = bulkTag.value.trim()
  if (!tag || selected.value.length === 0) return
  try {
    await api.resultsBulkUpdate({
      runIds: selected.value.map((run) => run.jobId),
      addTags: [tag],
    })
    bulkTag.value = ''
    clearSelection()
    await search()
  } catch {
    ElMessage.error(t('results.updateFailed'))
  }
}

function applyView(id: number | null): void {
  if (id == null) return
  const view = views.value.find((item) => item.id === id)
  if (!view) return
  query.value = view.filters.q
  favoritesOnly.value = view.filters.favorites
  tagFilter.value = [...view.filters.tags]
  void search()
}

async function saveView(): Promise<void> {
  const name = viewName.value.trim()
  if (!name) return
  try {
    const view = await api.resultsSaveView({
      name,
      filters: {
        q: query.value,
        favorites: favoritesOnly.value,
        tags: [...tagFilter.value],
      },
    })
    await loadViews()
    selectedView.value = view.id
    saveViewOpen.value = false
    viewName.value = ''
    ElMessage.success(t('results.viewSaved'))
  } catch {
    ElMessage.error(t('results.viewSaveFailed'))
  }
}

async function deleteView(): Promise<void> {
  if (selectedView.value == null) return
  try {
    await ElMessageBox.confirm(
      t('results.viewDeleteConfirm'),
      t('results.deleteView'),
      { type: 'warning' },
    )
  } catch {
    return // user cancelled
  }
  const view = views.value.find((item) => item.id === selectedView.value)
  try {
    await api.resultsDeleteView(selectedView.value)
    selectedView.value = null
    await loadViews()
    if (view) {
      undo.push(t('undo.deleteView', { name: view.name }), async () => {
        await api.resultsSaveView({ name: view.name, filters: view.filters })
        await loadViews()
      })
    }
  } catch {
    ElMessage.error(t('results.viewDeleteFailed'))
  }
}

onMounted(() => {
  void search()
  void loadViews()
})
</script>

<template>
  <div class="vs-page">
    <div class="vs-page__head">
      <div>
        <h1 class="vs-page__title">{{ t('results.title') }}</h1>
        <p class="vs-page__subtitle">{{ t('results.subtitle') }}</p>
      </div>
    </div>

    <section class="vs-card results-search">
      <el-input
        v-model="query"
        clearable
        :placeholder="t('results.placeholder')"
        :prefix-icon="Search"
        @keyup.enter="search"
      />
      <el-button type="primary" :loading="loading" @click="search">
        {{ t('common.search') }}
      </el-button>

      <div class="results-search__filters">
        <el-checkbox v-model="favoritesOnly" @change="() => search()">
          {{ t('results.favoritesOnly') }}
        </el-checkbox>
        <el-select
          v-model="tagFilter"
          multiple
          clearable
          collapse-tags
          size="small"
          class="results-search__tags"
          :placeholder="t('results.filterTags')"
          @change="() => search()"
        >
          <el-option
            v-for="tag in tags"
            :key="tag.tag"
            :label="`${tag.tag} (${tag.count})`"
            :value="tag.tag"
          />
        </el-select>
        <span class="results-search__spacer" />
        <el-select
          v-model="selectedView"
          clearable
          size="small"
          class="results-search__views"
          :placeholder="t('results.views')"
          @change="applyView"
        >
          <el-option v-for="view in views" :key="view.id" :label="view.name" :value="view.id" />
        </el-select>
        <el-button size="small" @click="saveViewOpen = true">{{ t('results.saveView') }}</el-button>
        <el-button v-if="selectedView" size="small" @click="deleteView">
          {{ t('results.deleteView') }}
        </el-button>
      </div>
    </section>

    <section class="vs-card results-table" v-loading="loading">
      <div v-if="loaded" class="results-table__count">
        {{ t('results.loadedCount', { n: rows.length }) }}
      </div>
      <el-alert
        v-if="error"
        type="error"
        :title="t('results.searchFailed')"
        show-icon
        :closable="false"
        class="results-table__alert"
      />
      <el-table
        v-if="rows.length > 0"
        :data="rows"
        stripe
        size="small"
        :max-height="520"
        row-key="jobId"
        :row-class-name="rowClassName"
      >
        <el-table-column width="40">
          <template #default="{ row }">
            <el-checkbox
              :model-value="isPicked(row.jobId)"
              @change="toggle(row)"
            />
          </template>
        </el-table-column>
        <el-table-column width="42">
          <template #default="{ row }">
            <el-button
              text
              size="small"
              :title="row.favorite ? t('results.unfavorite') : t('results.favorite')"
              @click.stop="toggleFavorite(row)"
            >
              <el-icon :color="row.favorite ? 'var(--vs-warning)' : undefined">
                <StarFilled v-if="row.favorite" />
                <Star v-else />
              </el-icon>
            </el-button>
          </template>
        </el-table-column>
        <el-table-column prop="createdAt" :label="t('results.colTime')" width="132">
          <template #default="{ row }">
            <span class="results-table__time">{{ formatTime(row.createdAt) }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="t('results.colLigand')">
          <template #default="{ row }">
            <div class="results-table__ligand">
              <span class="results-table__label" :title="row.label">
                {{ row.label || (row.isBatch ? t('results.batchRun') : '—') }}
              </span>
              <span v-if="row.matchedLigand" class="results-table__chip">
                {{ t('results.matched', { name: row.matchedLigand }) }}
              </span>
            </div>
          </template>
        </el-table-column>
        <el-table-column :label="t('results.colTags')" width="190">
          <template #default="{ row }">
            <div class="results-table__tags">
              <el-tag v-for="tag in row.tags" :key="tag" size="small" effect="plain">
                {{ tag }}
              </el-tag>
              <el-button text size="small" @click.stop="openTagEditor(row)">
                {{ t('results.editTags') }}
              </el-button>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="receptor" :label="t('results.colReceptor')" width="180">
          <template #default="{ row }">
            <span class="results-table__truncate" :title="row.receptor">
              {{ row.receptor || '—' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="scoring" :label="t('results.colScoring')" width="96">
          <template #default="{ row }">
            <span class="results-table__mono">{{ row.scoring || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column
          prop="bestAffinity"
          :label="t('results.colBest')"
          width="104"
          align="right"
        >
          <template #default="{ row }">
            <span
              class="results-table__best"
              :class="{ 'is-dim': !(row.status === 'completed' && row.bestAffinity !== null) }"
            >
              {{ row.bestAffinity === null ? '—' : row.bestAffinity.toFixed(2) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column width="88" :label="t('results.colStatus')">
          <template #default="{ row }">
            <span class="result-badge" :class="`result-badge--${row.status}`">
              {{ t(`docking.status.${row.status}`) }}
            </span>
          </template>
        </el-table-column>
      </el-table>
      <div v-if="rows.length > 0 && hasMore" class="results-table__more">
        <el-button size="small" :loading="loadingMore" @click="loadMore">
          {{ t('results.loadMore') }}
        </el-button>
      </div>
      <el-empty
        v-if="rows.length === 0 && !loading && loaded"
        :description="t('results.empty')"
        :image-size="72"
      >
        <p class="results-table__empty-hint">{{ t('results.emptyHint') }}</p>
      </el-empty>
    </section>
    <div v-if="selected.length >= 1" class="results-selectionbar">
      <span class="results-selectionbar__count">
        {{ t('results.selected', { n: selected.length }) }}
      </span>
      <el-input
        v-model="bulkTag"
        size="small"
        class="results-selectionbar__tag"
        :placeholder="t('results.bulkTagPlaceholder')"
        @keyup.enter="bulkAddTag"
      />
      <el-button size="small" @click="bulkAddTag">{{ t('results.addTag') }}</el-button>
      <el-button size="small" @click="bulkFavorite(true)">{{ t('results.favorite') }}</el-button>
      <el-button size="small" @click="bulkFavorite(false)">{{ t('results.unfavorite') }}</el-button>
      <el-button
        type="primary"
        :disabled="selected.length < 2 || selected.length > 4"
        :title="selected.length < 2 ? t('results.compareMin') : selected.length > 4 ? t('results.maxHint') : undefined"
        @click="openCompare"
      >
        {{ t('results.compare') }}
      </el-button>
      <el-button @click="clearSelection">{{ t('results.clear') }}</el-button>
    </div>

    <el-dialog
      v-model="compareOpen"
      :title="t('results.compareTitle', { n: selected.length })"
      width="min(1040px, 92vw)"
      class="results-compare"
    >
      <div v-if="compareLoading" v-loading="compareLoading" class="results-compare__loading" />
      <template v-else>
        <p v-if="compareError || compareRuns.length === 0" class="results-compare__failed">
          {{ t('results.detailFailed') }}
        </p>
        <div v-else class="results-compare__grid">
          <div v-for="run in compareRuns" :key="run.jobId" class="vs-card result-card">
            <div class="result-card__head">
              <span class="result-card__label" :title="run.label || run.jobId">
                {{ run.label || '—' }}
              </span>
              <span class="result-badge" :class="`result-badge--${run.status}`">
                {{ t(`docking.status.${run.status}`) }}
              </span>
            </div>
            <div class="result-card__score">
              <span
                class="result-card__affinity"
                :class="{ 'is-dim': !(run.status === 'completed' && run.bestAffinity !== null) }"
              >{{ affinityText(run) }}</span>
              <span class="result-card__unit">{{ t('results.kcal') }}</span>
            </div>
            <dl class="result-card__dl">
              <dt>{{ t('results.cardReceptor') }}</dt>
              <dd><span :class="{ 'is-missing': !run.receptor }">{{ run.receptor || '—' }}</span></dd>
              <dt>{{ t('results.cardScoring') }}</dt>
              <dd><span :class="{ 'is-missing': !run.scoring }">{{ run.scoring || '—' }}</span></dd>
              <dt>{{ t('results.cardTime') }}</dt>
              <dd><span :class="{ 'is-missing': !run.createdAt }">{{ formatTime(run.createdAt) }}</span></dd>
              <dt>{{ t('results.cardElapsed') }}</dt>
              <dd><span :class="{ 'is-missing': run.elapsedMs === null }">{{ formatElapsed(run.elapsedMs) }}</span></dd>
              <dt>{{ t('results.cardPoses') }}</dt>
              <dd><span :class="{ 'is-missing': !(run.nPoses > 0) }">{{ run.nPoses > 0 ? run.nPoses : '—' }}</span></dd>
              <template v-if="paramsText(run)">
                <dt>{{ t('results.cardParams') }}</dt>
                <dd>{{ paramsText(run) }}</dd>
              </template>
            </dl>
          </div>
        </div>
      </template>
    </el-dialog>

    <el-dialog v-model="tagDialogOpen" :title="t('results.tagsTitle')" width="420px">
      <div class="results-tag-editor">
        <el-tag
          v-for="tag in tagDraft"
          :key="tag"
          closable
          @close="removeTagDraft(tag)"
        >
          {{ tag }}
        </el-tag>
        <span v-if="tagDraft.length === 0" class="results-tag-editor__empty">
          {{ t('results.noTags') }}
        </span>
      </div>
      <div class="results-tag-editor__input">
        <el-input
          v-model="tagInput"
          size="small"
          :placeholder="t('results.tagPlaceholder')"
          @keyup.enter="addTagDraft"
        />
        <el-button size="small" @click="addTagDraft">{{ t('results.addTag') }}</el-button>
      </div>
      <template #footer>
        <el-button @click="tagDialogOpen = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" @click="saveTags">{{ t('common.save') }}</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="saveViewOpen" :title="t('results.saveView')" width="380px">
      <el-input
        v-model="viewName"
        :placeholder="t('results.viewNamePlaceholder')"
        @keyup.enter="saveView"
      />
      <template #footer>
        <el-button @click="saveViewOpen = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" @click="saveView">{{ t('results.saveView') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.results-search {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
  padding: 14px 18px;
}

.results-search .el-input {
  flex: 1 1 260px;
  min-width: 220px;
}

.results-search__filters {
  flex: 1 0 100%;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.results-search__tags {
  min-width: 180px;
}

.results-search__views {
  min-width: 160px;
}

.results-search__spacer {
  flex: 1;
}

.results-table {
  padding: 14px 18px;
}

.results-table__count {
  font-size: 12px;
  color: var(--vs-text-faint);
  margin-bottom: 8px;
}

.results-table__more {
  display: flex;
  justify-content: center;
  padding: 12px 0 2px;
}

.results-table__alert {
  margin-bottom: 8px;
}

.results-table .el-table {
  --el-table-header-bg-color: var(--vs-bg-sunken);
}

.results-table :deep(tr.is-picked > td.el-table__cell) {
  background: var(--vs-accent-soft);
}

.results-table__time,
.results-table__mono {
  font-family: var(--vs-font-mono);
  font-size: 12px;
}

.results-table__truncate,
.results-table__label {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.results-table__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
}

.results-table__ligand {
  display: flex;
  flex-direction: column;
  gap: 3px;
  align-items: flex-start;
}

.results-table__chip {
  font-size: 11px;
  color: var(--vs-warning);
  background: color-mix(in srgb, var(--vs-warning) 12%, transparent);
  border-radius: var(--vs-radius-sm);
  padding: 0 6px;
  white-space: nowrap;
}

.results-table__best {
  font-family: var(--vs-font-mono);
  font-size: 12px;
  color: var(--vs-accent);
}

.results-table__best.is-dim {
  color: var(--vs-text-faint);
}

.results-table__empty-hint {
  font-size: 12px;
  color: var(--vs-text-faint);
}

/* 选择条：底部居中胶囊，浮在内容与状态栏（--vs-statusbar-height）之上 */
.results-selectionbar {
  position: fixed;
  z-index: 30;
  left: 50%;
  bottom: calc(var(--vs-statusbar-height) + 16px);
  transform: translateX(-50%);
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  max-width: 92vw;
  padding: 8px 14px;
  background: var(--vs-bg-surface);
  border: 1px solid var(--vs-border);
  border-radius: var(--vs-radius);
  box-shadow: var(--vs-shadow);
}

.results-selectionbar__count {
  font-size: 13px;
  color: var(--vs-text-muted);
}

.results-selectionbar__tag {
  width: 140px;
}

.results-tag-editor {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  min-height: 28px;
}

.results-tag-editor__empty {
  font-size: 12px;
  color: var(--vs-text-faint);
}

.results-tag-editor__input {
  display: flex;
  gap: 8px;
  margin-top: 12px;
}

.results-compare__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 12px;
}

.results-compare__loading {
  min-height: 120px;
}

.results-compare__failed {
  font-size: 13px;
  color: var(--vs-text-faint);
  text-align: center;
  padding: 12px 0;
}

.result-card {
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.result-card__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.result-card__label {
  font-size: 14px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.result-card__score {
  display: flex;
  align-items: baseline;
  gap: 6px;
}

.result-card__affinity {
  font-family: var(--vs-font-mono);
  font-size: 20px;
  color: var(--vs-accent);
}

.result-card__affinity.is-dim {
  color: var(--vs-text-faint);
}

.result-card__unit {
  font-size: 11px;
  color: var(--vs-text-faint);
}

.result-card__dl {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 4px 10px;
  font-size: 12px;
  margin: 0;
}

.result-card__dl dt {
  color: var(--vs-text-faint);
}

.result-card__dl dd {
  margin: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.result-card__dl .is-missing {
  color: var(--vs-text-faint);
}

.result-badge {
  font-family: var(--vs-font-mono);
  font-size: 11px;
  border-radius: var(--vs-radius-sm);
  padding: 1px 6px;
  white-space: nowrap;
}

.result-badge--completed {
  color: var(--vs-success);
  background: color-mix(in srgb, var(--vs-success) 14%, transparent);
}

.result-badge--failed {
  color: var(--vs-danger);
  background: color-mix(in srgb, var(--vs-danger) 14%, transparent);
}

.result-badge--cancelled {
  color: var(--vs-text-faint);
  background: color-mix(in srgb, var(--vs-text-faint) 14%, transparent);
}
</style>
