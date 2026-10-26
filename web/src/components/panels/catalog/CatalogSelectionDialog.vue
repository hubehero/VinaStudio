<script setup lang="ts">
import { Search } from '@element-plus/icons-vue'
import { ElAutoResizer, ElButton, ElCheckbox, ElDialog, ElInput, ElInputNumber, ElMessage, ElMessageBox, ElOption, ElOptionGroup, ElSelect, ElTableV2 } from 'element-plus'
import type { Column } from 'element-plus'
import { computed, h, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { api } from '@/api/http'
import type {
  CatalogCollection,
  CatalogLibrary,
  CatalogMolecule,
  CatalogSelection,
  CatalogStudy,
} from '@/types/api'

const props = withDefaults(defineProps<{ modelValue: boolean; title?: string }>(), {
  title: '',
})
const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  selected: [selection: CatalogSelection]
}>()

const { t } = useI18n()

const studies = ref<CatalogStudy[]>([])
const collections = ref<CatalogCollection[]>([])
const libraries = ref<CatalogLibrary[]>([])
const scope = ref('all')
const query = ref('')
const preparedOnly = ref(false)
const mwMin = ref<number | null>(null)
const mwMax = ref<number | null>(null)
const qedMin = ref<number | null>(null)
const tpsaMax = ref<number | null>(null)
const logpMax = ref<number | null>(null)
const rows = ref<CatalogMolecule[]>([])
const total = ref(0)
const offset = ref(0)
const limit = 100
const loading = ref(false)
const creating = ref(false)
const selectedIds = ref<string[]>([])
let generation = 0

const page = computed(() => Math.floor(offset.value / limit) + 1)
const pages = computed(() => Math.max(1, Math.ceil(total.value / limit)))
const hasSelection = computed(() => selectedIds.value.length > 0)

const scopeGroups = computed(() => [
  {
    label: t('selection.scopeGeneral'),
    options: [
      { value: 'all', label: t('selection.all') },
      { value: 'unassigned', label: t('catalog.unassigned') },
    ],
  },
  {
    label: t('catalog.studies'),
    options: studies.value.map((item) => ({ value: `study:${item.id}`, label: item.name })),
  },
  {
    label: t('catalog.collections'),
    options: collections.value.map((item) => ({
      value: `collection:${item.id}`,
      label: item.name,
    })),
  },
  {
    label: t('catalog.libraries'),
    options: libraries.value.map((item) => ({ value: `library:${item.id}`, label: item.name })),
  },
])

function scopeFilters(): Record<string, string[]> {
  if (scope.value.startsWith('study:')) return { study_id: [scope.value.slice(6)] }
  if (scope.value.startsWith('collection:')) {
    return { collection_id: [scope.value.slice(11)] }
  }
  if (scope.value.startsWith('library:')) return { library_id: [scope.value.slice(8)] }
  if (scope.value === 'unassigned') return { unassigned: ['true'] }
  return {}
}

function selectionFilters(): Record<string, string[]> {
  const filters = scopeFilters()
  if (preparedOnly.value) filters.prep_status = ['prepared']
  if (mwMin.value !== null) filters.mw_min = [String(mwMin.value)]
  if (mwMax.value !== null) filters.mw_max = [String(mwMax.value)]
  if (qedMin.value !== null) filters.qed = [`>=${qedMin.value}`]
  if (tpsaMax.value !== null) filters.tpsa = [`<=${tpsaMax.value}`]
  if (logpMax.value !== null) filters.logp = [`<=${logpMax.value}`]
  return filters
}

function searchParams(): Record<string, string | number | boolean | undefined> {
  const params: Record<string, string | number | boolean | undefined> = {
    q: query.value,
    limit,
    offset: offset.value,
    sort: 'updated',
  }
  if (scope.value.startsWith('study:')) params.study_id = scope.value.slice(6)
  if (scope.value.startsWith('collection:')) params.collection_id = scope.value.slice(11)
  if (scope.value.startsWith('library:')) params.library_id = scope.value.slice(8)
  if (scope.value === 'unassigned') params.unassigned = true
  if (preparedOnly.value) params.prep = 'prepared'
  if (mwMin.value !== null) params.mw_min = mwMin.value
  if (mwMax.value !== null) params.mw_max = mwMax.value
  if (qedMin.value !== null) params.qed = `>=${qedMin.value}`
  if (tpsaMax.value !== null) params.tpsa = `<=${tpsaMax.value}`
  if (logpMax.value !== null) params.logp = `<=${logpMax.value}`
  return params
}

async function search(reset = false): Promise<void> {
  if (reset) {
    offset.value = 0
    selectedIds.value = []
  }
  const requestGeneration = ++generation
  loading.value = true
  try {
    const result = await api.catalogSearch(searchParams())
    if (requestGeneration !== generation) return
    rows.value = result.items
    total.value = result.total
  } catch (cause) {
    if (requestGeneration === generation) {
      ElMessage.error(cause instanceof Error ? cause.message : String(cause))
    }
  } finally {
    if (requestGeneration === generation) loading.value = false
  }
}

async function loadScopes(): Promise<void> {
  try {
    const [nextStudies, nextCollections, nextLibraries] = await Promise.all([
      api.catalogStudies(),
      api.catalogCollections(),
      api.catalogLibraries(),
    ])
    studies.value = nextStudies
    collections.value = nextCollections
    libraries.value = nextLibraries
  } catch {
    // Scope lists are optional; the all/unassigned choices still work.
  }
}

function toggleSelected(id: string): void {
  selectedIds.value = selectedIds.value.includes(id)
    ? selectedIds.value.filter((item) => item !== id)
    : [...selectedIds.value, id]
}

function rowClass({ rowData }: { rowData: CatalogMolecule }): string {
  return selectedIds.value.includes(rowData.id) ? 'selection-row--selected' : ''
}

const columns = computed<Column<CatalogMolecule>[]>(() => [
  {
    key: 'select',
    width: 42,
    cellRenderer: ({ rowData }) =>
      h('input', {
        type: 'checkbox',
        checked: selectedIds.value.includes(rowData.id),
        'aria-label': `${t('common.select')} ${rowData.name}`,
        onChange: () => toggleSelected(rowData.id),
      }),
  },
  {
    key: 'name',
    dataKey: 'name',
    title: t('catalog.name'),
    width: 260,
    cellRenderer: ({ rowData }) =>
      h(
        'button',
        {
          type: 'button',
          class: 'selection-name',
          onClick: () => toggleSelected(rowData.id),
        },
        rowData.name,
      ),
  },
  {
    key: 'kind',
    title: t('catalog.kind'),
    width: 86,
    cellRenderer: ({ rowData }) => rowData.kindHint,
  },
  {
    key: 'mw',
    title: t('catalog.mw'),
    width: 86,
    align: 'right',
    cellRenderer: ({ rowData }) =>
      rowData.molecularWeight === null ? '—' : rowData.molecularWeight.toFixed(1),
  },
  {
    key: 'qed',
    title: 'QED',
    width: 76,
    align: 'right',
    cellRenderer: ({ rowData }) => (rowData.qed === null ? '—' : rowData.qed.toFixed(2)),
  },
  {
    key: 'prep',
    title: t('catalog.prep'),
    width: 100,
    cellRenderer: ({ rowData }) => rowData.prepStatus,
  },
])

async function persistSelection(allMatching: boolean): Promise<CatalogSelection | null> {
  if (allMatching && total.value === 0) return null
  if (!allMatching && selectedIds.value.length === 0) return null
  try {
    const selection = await api.catalogCreateSelection({
      name: allMatching ? t('selection.allMatchingName') : t('selection.manualName'),
      source: allMatching ? 'query' : 'ids',
      spec: {
        q: query.value,
        filters: selectionFilters(),
        maxMembers: 50000,
      },
      ...(allMatching ? {} : { moleculeIds: selectedIds.value }),
    })
    if (selection.truncated) {
      ElMessage.warning(t('selection.truncated', { n: selection.memberCount }))
    }
    return selection
  } catch (cause) {
    ElMessage.error(cause instanceof Error ? cause.message : String(cause))
    return null
  }
}

async function createSelection(allMatching: boolean): Promise<void> {
  creating.value = true
  try {
    const selection = await persistSelection(allMatching)
    if (selection === null) return
    emit('selected', selection)
    emit('update:modelValue', false)
  } finally {
    creating.value = false
  }
}

async function saveAsLibrary(allMatching: boolean): Promise<void> {
  let name = ''
  try {
    const result = await ElMessageBox.prompt(
      t('selection.libraryNameHint'),
      t('selection.saveLibrary'),
      {
        inputValue: t('selection.libraryDefault'),
        inputPattern: /\S+/,
        inputErrorMessage: t('catalog.nameRequired'),
      },
    )
    name = result.value.trim()
  } catch {
    return
  }
  creating.value = true
  try {
    const selection = await persistSelection(allMatching)
    if (selection === null) return
    await api.catalogCreateLibrary({ name, selectionId: selection.id })
    ElMessage.success(t('selection.librarySaved', { n: selection.memberCount }))
    emit('selected', selection)
    emit('update:modelValue', false)
  } catch (cause) {
    ElMessage.error(cause instanceof Error ? cause.message : String(cause))
  } finally {
    creating.value = false
  }
}

function close(): void {
  emit('update:modelValue', false)
}

watch(
  () => props.modelValue,
  (open) => {
    if (!open) return
    void loadScopes()
    void search(true)
  },
)

watch([scope, preparedOnly], () => {
  void search(true)
})
</script>

<template>
  <ElDialog
    :model-value="modelValue"
    :title="title || t('selection.title')"
    width="900px"
    destroy-on-close
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div class="selection-toolbar">
      <ElSelect v-model="scope" size="small" style="width: 190px">
        <ElOptionGroup
          v-for="group in scopeGroups"
          :key="group.label"
          :label="group.label"
        >
          <ElOption
            v-for="option in group.options"
            :key="option.value"
            :label="option.label"
            :value="option.value"
          />
        </ElOptionGroup>
      </ElSelect>
      <ElInput
        v-model="query"
        size="small"
        clearable
        :placeholder="t('catalog.searchPlaceholder')"
        @keyup.enter="search(true)"
      />
      <ElButton size="small" :icon="Search" @click="search(true)">
        {{ t('catalog.search') }}
      </ElButton>
    </div>

    <div class="selection-filters">
      <label>
        MW
        <ElInputNumber v-model="mwMin" :min="0" :controls="false" size="small" />
        –
        <ElInputNumber v-model="mwMax" :min="0" :controls="false" size="small" />
      </label>
      <label>
        QED ≥
        <ElInputNumber v-model="qedMin" :min="0" :max="1" :step="0.05" :controls="false" size="small" />
      </label>
      <label>
        TPSA ≤
        <ElInputNumber v-model="tpsaMax" :min="0" :controls="false" size="small" />
      </label>
      <label>
        LogP ≤
        <ElInputNumber v-model="logpMax" :step="0.5" :controls="false" size="small" />
      </label>
      <label class="selection-prepared">
        <el-checkbox v-model="preparedOnly">{{ t('selection.preparedOnly') }}</el-checkbox>
      </label>
    </div>

    <div v-loading="loading" class="selection-table">
      <ElAutoResizer>
        <template #default="{ width, height }">
          <ElTableV2
            :columns="columns"
            :data="rows"
            :width="width"
            :height="height"
            :row-height="38"
            row-key="id"
            :row-class="rowClass"
          />
        </template>
      </ElAutoResizer>
    </div>

    <footer class="selection-footer">
      <span>{{ t('catalog.total', { n: total }) }}</span>
      <span class="selection-count">
        {{ t('catalog.selected', { n: selectedIds.length }) }}
      </span>
      <ElButton size="small" :disabled="offset === 0" @click="offset -= limit; search()">
        ‹
      </ElButton>
      <span>{{ page }} / {{ pages }}</span>
      <ElButton
        size="small"
        :disabled="offset + limit >= total"
        @click="offset += limit; search()"
      >
        ›
      </ElButton>
    </footer>

    <template #footer>
      <ElButton @click="close">{{ t('common.cancel') }}</ElButton>
      <ElButton
        :disabled="!hasSelection || creating"
        :loading="creating"
        @click="createSelection(false)"
      >
        {{ t('selection.useSelected', { n: selectedIds.length }) }}
      </ElButton>
      <ElButton
        :disabled="(selectedIds.length === 0 && total === 0) || creating"
        :loading="creating"
        @click="saveAsLibrary(selectedIds.length === 0)"
      >
        {{ t('selection.saveLibrary') }}
      </ElButton>
      <ElButton
        type="primary"
        :disabled="total === 0 || creating"
        :loading="creating"
        @click="createSelection(true)"
      >
        {{ t('selection.useAll', { n: total }) }}
      </ElButton>
    </template>
  </ElDialog>
</template>

<style scoped>
.selection-toolbar {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
}
.selection-toolbar :deep(.el-input) {
  flex: 1;
}
.selection-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 14px;
  align-items: center;
  margin-bottom: 8px;
  font-size: 12px;
  color: var(--vs-text-muted);
}
.selection-filters label {
  display: flex;
  gap: 4px;
  align-items: center;
}
.selection-filters :deep(.el-input-number) {
  width: 72px;
}
.selection-prepared {
  margin-left: auto;
}
.selection-table {
  height: 380px;
  overflow: hidden;
  border: 1px solid var(--vs-border);
  border-radius: var(--vs-radius);
}
.selection-name {
  max-width: 100%;
  overflow: hidden;
  padding: 0;
  font: inherit;
  color: inherit;
  text-align: left;
  text-overflow: ellipsis;
  white-space: nowrap;
  cursor: pointer;
  background: transparent;
  border: 0;
}
.selection-name:hover {
  color: var(--vs-accent);
  text-decoration: underline;
}
.selection-footer {
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: flex-end;
  margin-top: 8px;
  font-size: 12px;
  color: var(--vs-text-muted);
}
.selection-count {
  margin-right: auto;
}
:deep(.selection-row--selected) {
  background: var(--vs-accent-soft);
}
</style>
