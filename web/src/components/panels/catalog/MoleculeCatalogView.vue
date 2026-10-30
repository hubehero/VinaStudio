<script setup lang="ts">
import { CopyDocument, MoreFilled, Search, Upload } from '@element-plus/icons-vue'
import { ElAutoResizer, ElMessage, ElMessageBox, ElPopover, ElTableV2 } from 'element-plus'
import type { Column } from 'element-plus'
import { computed, h, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import { pickFiles, pickFileForUpload } from '@/api/bridge'
import { api } from '@/api/http'
import CatalogPrepareDialog from '@/components/panels/catalog/CatalogPrepareDialog.vue'
import MoleculeLibraryDialog from '@/components/panels/MoleculeLibraryDialog.vue'
import SketcherDialog from '@/components/sketcher/SketcherDialog.vue'
import ViewportCanvas from '@/components/viewer/ViewportCanvas.vue'
import { useCatalogStore } from '@/stores/catalog'
import { defaultReceptorOptions } from '@/stores/preparation-shared'
import { chineseAlias } from '@/utils/catalog-name'
import { CATALOG_COLUMNS, useSettingsStore } from '@/stores/settings'
import type { CatalogLibraryMember, CatalogMolecule, CatalogStudyMember, SampleFile } from '@/types/api'

const { t } = useI18n()
const router = useRouter()
const store = useCatalogStore()
const settings = useSettingsStore()

const targetStudyId = ref('')
const targetCollectionId = ref('')
const showSuggestions = ref(false)
const importing = ref(false)
const prepareOpen = ref(false)
const tagInput = ref('')
const aliasInput = ref('')
const bulkTagInput = ref('')
const smilesOpen = ref(false)
const smilesText = ref('')
const smilesName = ref('')
const smilesBusy = ref(false)
const libraryDialog = ref<InstanceType<typeof MoleculeLibraryDialog> | null>(null)
const sketcher = ref<InstanceType<typeof SketcherDialog> | null>(null)
const samples = ref<SampleFile[]>([])

onMounted(() => {
  void store.refresh()
  void api.samples().then((items) => { samples.value = items }).catch(() => undefined)
})

const active = computed(() => store.activeMolecule)
const isReceptor = computed(() => active.value?.kindHint === 'receptor')

function metadataText(key: string): string | null {
  const value = active.value?.metadata?.[key]
  if (typeof value === 'string' && value.trim()) return value
  if (typeof value === 'number') return String(value)
  return null
}

const receptorRows = computed(() => {
  const mol = active.value
  if (!mol || mol.kindHint !== 'receptor') return []
  const pdbId = metadataText('pdbId')
    ?? (mol.identityKey.startsWith('pdb:') ? mol.identityKey.slice(4) : null)
    ?? mol.sourceId
  const recordedUrl = mol.sources.find((item) => item.url)?.url
  const sourceUrl = recordedUrl && /^https?:\/\//i.test(recordedUrl)
    ? recordedUrl
    : pdbId
      ? `https://www.rcsb.org/structure/${pdbId}`
      : null
  const classZh = metadataText('classZh')
  const targetClass = metadataText('targetClass')
  const classText = [classZh, targetClass].filter(Boolean).join(' · ')
  const resolution = metadataText('resolution')
  const ligand = metadataText('ligand')
  const ligandText = ligand
    ? ['none', 'apo', '—', '-', 'n/a'].includes(ligand.trim().toLowerCase())
      ? t('catalog.noCoLigand')
      : ligand
    : null
  return [
    { label: t('catalog.pdbId'), value: pdbId, href: sourceUrl },
    {
      label: t('catalog.proteinMass'),
      value: mol.molecularWeight ? `${mol.molecularWeight.toFixed(1)} Da` : null,
    },
    { label: t('catalog.targetClass'), value: classText || null },
    { label: t('catalog.gene'), value: metadataText('gene') },
    { label: t('catalog.organism'), value: metadataText('organism') },
    { label: t('catalog.chains'), value: metadataText('chain') },
    { label: t('catalog.coLigand'), value: ligandText },
    { label: t('catalog.method'), value: metadataText('method') },
    { label: t('catalog.resolution'), value: resolution ? `${resolution} Å` : null },
  ].filter((row) => row.value)
})

const receptorNote = computed(() => (isReceptor.value ? metadataText('note') : null))
const studyMembers = computed<CatalogStudyMember[]>(() => {
  const detail = store.scopeDetail
  return store.scope.kind === 'study' && detail && 'members' in detail
    ? (detail.members as CatalogStudyMember[])
    : []
})
const libraryMembers = computed<CatalogLibraryMember[]>(() => {
  const detail = store.scopeDetail
  return store.scope.kind === 'library' && detail && 'members' in detail
    ? (detail.members as CatalogLibraryMember[])
    : []
})
const collectionCount = computed(() => {
  const detail = store.scopeDetail
  return store.scope.kind === 'collection' && detail && 'moleculeCount' in detail
    ? detail.moleculeCount
    : 0
})

const libraryPreparedCount = computed(
  () => libraryMembers.value.filter((member) => member.preparedPath !== null).length,
)

const selectedCount = computed(() => store.selectedIds.length)
const flatScope = computed(
  () => store.scope.kind === 'library' || store.scope.kind === 'collection',
)

const activeFilterCount = computed(
  () => (store.sourceFilter ? 1 : 0) + (store.status ? 1 : 0) + (store.tagFilter ? 1 : 0),
)

function handleCatalogCommand(command: string): void {
  if (command === 'smiles') smilesOpen.value = true
  else if (command === 'draw') sketcher.value?.open()
  else if (command === 'library') libraryDialog.value?.open()
  else if (command === 'suggestions') showSuggestions.value = !showSuggestions.value
  else if (command === 'saveView') void saveCurrentView()
  else if (command.startsWith('sample:')) {
    const sample = samples.value.find((item) => `sample:${item.path}` === command)
    if (sample) void importSample(sample)
  }
}

const readableTagFacets = computed(() =>
  store.facets.tags.filter(
    (item) =>
      item.value !== 'builtin'
      && item.value !== 'undergraduate'
      && !item.value.startsWith('class:')
      && !item.value.startsWith('target_class:'),
  ),
)
const visibleTagFacets = computed(() => {
  const top = readableTagFacets.value.slice(0, 6)
  const selected = store.tagFilter
    ? readableTagFacets.value.find((item) => item.value === store.tagFilter)
    : undefined
  return selected && !top.some((item) => item.value === selected.value)
    ? [selected, ...top]
    : top
})
const hiddenTagFacets = computed(() =>
  readableTagFacets.value.filter(
    (item) => !visibleTagFacets.value.some((visible) => visible.value === item.value),
  ),
)
const tagFacetQuery = ref('')
const filteredHiddenTags = computed(() => {
  const needle = tagFacetQuery.value.trim().toLowerCase()
  return needle
    ? hiddenTagFacets.value.filter((item) => item.value.toLowerCase().includes(needle))
    : hiddenTagFacets.value
})
const hasFacets = computed(
  () =>
    store.facets.source.length > 0
    || store.facets.status.length > 0
    || readableTagFacets.value.length > 0,
)

function columnVisible(key: string): boolean {
  return settings.catalog.columns.includes(key)
}

function toggleColumn(key: string): void {
  const current = settings.catalog.columns
  settings.catalog.columns = current.includes(key)
    ? current.filter((item) => item !== key)
    : [...current, key]
}

function columnLabel(key: string): string {
  return t(`catalog.${key === 'prep' ? 'prep' : key}`)
}

function kindLabel(value: string): string {
  if (value === 'receptor') return t('molecules.typeReceptor')
  if (value === 'ligand') return t('molecules.typeLigand')
  return t('common.unknown')
}

function prepLabel(value: string): string {
  if (value === 'prepared') return t('catalog.prepared')
  if (value === 'unprepared' || value === 'unknown') return t('catalog.unprepared')
  return value
}

function resetColumns(): void {
  settings.catalog.columns = [...CATALOG_COLUMNS]
}

function scopeLabel(): string {
  if (store.scope.kind === 'study') return store.scope.name
  if (store.scope.kind === 'collection') return store.scope.name
  if (store.scope.kind === 'library') return store.scope.name
  if (store.scope.kind === 'unassigned') return t('catalog.unassigned')
  return t('catalog.all')
}

function rowClass({ rowData }: { rowData: CatalogMolecule }): string {
  return rowData.id === store.activeId ? 'catalog-row--active' : ''
}

const tableRowEvents = {
  onClick: ({ rowData }: { rowData: CatalogMolecule }) => store.selectMolecule(rowData.id),
}

const tableColumns = computed<Column<CatalogMolecule>[]>(() => {
  const columns: Column<CatalogMolecule>[] = [
    {
      key: 'select',
      width: 42,
      cellRenderer: ({ rowData }) =>
        h('input', {
          type: 'checkbox',
          checked: store.selectedIds.includes(rowData.id),
          'aria-label': `${t('common.select')} ${rowData.name}`,
          onChange: () => store.toggleSelected(rowData.id),
        }),
    },
  ]
  if (columnVisible('name')) {
    columns.push({
      key: 'name',
      dataKey: 'name',
      title: t('catalog.name'),
      width: 170,
      flexGrow: 1,
      cellRenderer: ({ rowData }) => {
        const zh = chineseAlias(rowData.aliases)
        return h('div', { class: 'catalog-name-cell' }, [
          h(
            'button',
            {
              type: 'button',
              class: 'catalog-name-link',
              title: rowData.name,
              onClick: () => store.selectMolecule(rowData.id),
            },
            rowData.name,
          ),
          zh ? h('span', { class: 'catalog-name-zh', title: zh }, zh) : null,
        ])
      },
    })
  }
  if (!flatScope.value && columnVisible('kind')) {
    columns.push({
      key: 'kind',
      title: t('catalog.kind'),
      width: 64,
      cellRenderer: ({ rowData }) => h('span', kindLabel(rowData.kindHint)),
    })
  }
  if (columnVisible('prep')) {
    columns.push({
      key: 'prep',
      title: t('catalog.prep'),
      width: 70,
      cellRenderer: ({ rowData }) => h('span', prepLabel(rowData.prepStatus)),
    })
  }
  if (columnVisible('mw')) {
    columns.push({
      key: 'mw',
      title: t('catalog.mw'),
      width: 76,
      align: 'right',
      cellRenderer: ({ rowData }) =>
        rowData.molecularWeight === null ? '—' : rowData.molecularWeight.toFixed(1),
    })
  }
  if (columnVisible('tags')) {
    columns.push({
      key: 'tags',
      title: t('catalog.tags'),
      width: 120,
      cellRenderer: ({ rowData }) => {
        const visible = rowData.tags
          .filter((tag: string) => tag !== 'builtin' && tag !== 'undergraduate' && !tag.startsWith('class:') && !tag.startsWith('target_class:'))
          .slice(0, 2)
        return h(
          'span',
          { class: 'catalog-tag-cell' },
          visible.length
            ? visible.map((tag: string) => h('span', { class: 'catalog-tag' }, tag))
            : '—',
        )
      },
    })
  }
  return columns
})

async function importMolecules(): Promise<void> {
  importing.value = true
  try {
    let paths = await pickFiles({
      title: t('catalog.import'),
      filters: '',
      multiple: true,
    })
    if (paths.length === 0) {
      const files = await pickFileForUpload(
        ['.pdb', '.pdbqt', '.sdf', '.mol', '.mol2', '.cif', '.mmcif'],
        true,
      )
      for (const file of files) {
        const saved = await api.upload(file)
        paths = [...paths, saved.path]
      }
    }
    if (paths.length === 0) return
    const imported = await api.catalogImport({ paths, kindHint: 'unknown' })
    await store.refresh()
    ElMessage.success(t('catalog.imported', { n: imported.length }))
  } catch (cause) {
    ElMessage.error(cause instanceof Error ? cause.message : String(cause))
  } finally {
    importing.value = false
  }
}

async function importPaths(paths: string[]): Promise<void> {
  const imported = await api.catalogImport({ paths, kindHint: 'unknown' })
  await store.refresh()
  ElMessage.success(t('catalog.imported', { n: imported.length }))
}

async function importSmiles(text: string, name?: string): Promise<void> {
  const lines = text.split(/\r?\n/).map((line) => line.trim()).filter(Boolean)
  if (lines.length === 0 || smilesBusy.value) return
  smilesBusy.value = true
  try {
    const items = await api.ligandFromSmiles({
      smilesList: lines,
      name: name?.trim() || null,
    })
    await importPaths(items.map((item) => item.path))
    smilesOpen.value = false
    smilesText.value = ''
    smilesName.value = ''
  } catch (cause) {
    ElMessage.error(cause instanceof Error ? cause.message : String(cause))
  } finally {
    smilesBusy.value = false
  }
}

async function submitSmiles(): Promise<void> {
  await importSmiles(smilesText.value, smilesName.value)
}

async function onSketched(smiles: string): Promise<void> {
  await importSmiles(smiles)
}

async function importSample(sample: SampleFile): Promise<void> {
  try {
    await importPaths([sample.path])
  } catch (cause) {
    ElMessage.error(cause instanceof Error ? cause.message : String(cause))
  }
}


async function promptName(title: string): Promise<string | null> {
  try {
    const result = await ElMessageBox.prompt(title, t('catalog.name'), {
      confirmButtonText: t('common.ok'),
      cancelButtonText: t('common.cancel'),
      inputPattern: /\S+/,
      inputErrorMessage: t('catalog.nameRequired'),
    })
    return result.value.trim()
  } catch {
    return null
  }
}

async function createStudy(): Promise<void> {
  const name = await promptName(t('catalog.createStudy'))
  if (!name) return
  try {
    const study = await store.createStudy(name)
    store.setScope({ kind: 'study', id: study.id, name: study.name })
    ElMessage.success(t('catalog.created'))
  } catch (cause) {
    ElMessage.error(cause instanceof Error ? cause.message : String(cause))
  }
}

async function createCollection(): Promise<void> {
  const name = await promptName(t('catalog.createCollection'))
  if (!name) return
  try {
    const parentId = store.scope.kind === 'collection' ? store.scope.id : null
    const collection = await store.createCollection(name, parentId)
    store.setScope({ kind: 'collection', id: collection.id, name: collection.name })
    ElMessage.success(t('catalog.created'))
  } catch (cause) {
    ElMessage.error(cause instanceof Error ? cause.message : String(cause))
  }
}

async function createLibrary(): Promise<void> {
  const name = await promptName(t('catalog.createLibrary'))
  if (!name) return
  try {
    const library = await store.createLibrary(name)
    store.setScope({ kind: 'library', id: library.id, name: library.name })
    ElMessage.success(t('catalog.created'))
  } catch (cause) {
    ElMessage.error(cause instanceof Error ? cause.message : String(cause))
  }
}

async function addToStudy(): Promise<void> {
  if (!targetStudyId.value) return
  try {
    await store.addSelectedToStudy(targetStudyId.value)
    ElMessage.success(t('catalog.added'))
  } catch (cause) {
    ElMessage.error(cause instanceof Error ? cause.message : String(cause))
  }
}

async function addToCollection(): Promise<void> {
  if (!targetCollectionId.value) return
  try {
    await store.addSelectedToCollection(targetCollectionId.value)
    ElMessage.success(t('catalog.added'))
  } catch (cause) {
    ElMessage.error(cause instanceof Error ? cause.message : String(cause))
  }
}

const receptorUrl = computed(() => {
  const mol = active.value
  if (!mol || mol.kindHint !== 'receptor') return null
  return `/api/catalog/molecules/${encodeURIComponent(mol.id)}/preview`
})

const ligandUrl = computed(() => {
  const mol = active.value
  if (!mol || mol.kindHint === 'receptor') return null
  return `/api/catalog/molecules/${encodeURIComponent(mol.id)}/preview3d`
})

async function copySmiles(): Promise<void> {
  const value = active.value?.canonicalSmiles
  if (!value) return
  try {
    await navigator.clipboard.writeText(value)
    ElMessage.success(t('catalog.smilesCopied'))
  } catch {
    ElMessage.error(t('common.copyFailed'))
  }
}

async function saveCurrentView(): Promise<void> {
  const name = await promptName(t('catalog.saveView'))
  if (!name) return
  try {
    await store.saveCurrentView(name)
    ElMessage.success(t('catalog.viewSaved'))
  } catch (cause) {
    ElMessage.error(cause instanceof Error ? cause.message : String(cause))
  }
}

async function applyView(id: string): Promise<void> {
  const view = store.savedViews.find((item) => item.id === id)
  if (view) await store.applySavedView(view)
}

async function removeView(id: string): Promise<void> {
  await store.deleteSavedView(id)
}

async function removeActive(): Promise<void> {
  const mol = active.value
  if (!mol) return
  try {
    await ElMessageBox.confirm(t('catalog.removeMoleculeConfirm', { name: mol.name }), { type: 'warning' })
  } catch {
    return
  }
  await store.deleteMolecule(mol.id)
  ElMessage.success(t('catalog.deleted'))
}

async function addBulkTag(): Promise<void> {
  const tag = bulkTagInput.value.trim()
  if (!tag) return
  await store.bulkTag(tag)
  bulkTagInput.value = ''
  ElMessage.success(t('catalog.tagged'))
}

async function renameScope(): Promise<void> {
  const current = store.scope
  if (current.kind === 'all' || current.kind === 'unassigned') return
  const name = await promptName(t('catalog.rename'))
  if (!name) return
  try {
    await store.renameScope(name)
    ElMessage.success(t('catalog.renamed'))
  } catch (cause) {
    ElMessage.error(cause instanceof Error ? cause.message : String(cause))
  }
}

async function removeScopeMember(moleculeId: string, role?: string): Promise<void> {
  try {
    await ElMessageBox.confirm(t('catalog.removeMemberConfirm'), { type: 'warning' })
  } catch {
    return
  }
  if (store.scope.kind === 'study' && role) {
    await store.removeStudyMember(moleculeId, role)
  } else if (store.scope.kind === 'library') {
    await store.removeLibraryMember(moleculeId)
  } else if (store.scope.kind === 'collection') {
    await store.removeCollectionMember(moleculeId)
  }
  ElMessage.success(t('catalog.memberRemoved'))
}

async function removeStudy(id: string, name: string): Promise<void> {
  try {
    await ElMessageBox.confirm(t('catalog.deleteConfirm', { name }), { type: 'warning' })
  } catch {
    return
  }
  await store.deleteStudy(id)
  if (store.scope.kind === 'study' && store.scope.id === id) store.setScope({ kind: 'all' })
  ElMessage.success(t('catalog.deleted'))
}

async function removeCollection(id: string, name: string): Promise<void> {
  try {
    await ElMessageBox.confirm(t('catalog.deleteConfirm', { name }), { type: 'warning' })
  } catch {
    return
  }
  await store.deleteCollection(id)
  if (store.scope.kind === 'collection' && store.scope.id === id) store.setScope({ kind: 'all' })
  ElMessage.success(t('catalog.deleted'))
}

async function removeLibrary(id: string, name: string): Promise<void> {
  try {
    await ElMessageBox.confirm(t('catalog.deleteConfirm', { name }), { type: 'warning' })
  } catch {
    return
  }
  await store.deleteLibrary(id)
  if (store.scope.kind === 'library' && store.scope.id === id) store.setScope({ kind: 'all' })
  ElMessage.success(t('catalog.deleted'))
}

function suggestionTitle(suggestion: { kind: string; title: string; payload: Record<string, unknown>; moleculeIds: string[] }): string {
  if (suggestion.kind === 'study_pairs') {
    return t('catalog.suggestionStudyTitle', { id: String(suggestion.payload.pdbId ?? '') })
  }
  if (suggestion.kind === 'role') {
    const name = store.molecules.find((item) => item.id === suggestion.moleculeIds[0])?.name
    return t('catalog.suggestionRoleTitle', { name: name ?? suggestion.title })
  }
  if (suggestion.kind === 'duplicates') {
    return t('catalog.suggestionDuplicatesTitle', { n: suggestion.moleculeIds.length })
  }
  if (suggestion.kind === 'prepare') {
    const name = store.molecules.find((item) => item.id === suggestion.moleculeIds[0])?.name
    return t('catalog.suggestionPrepareTitle', { name: name ?? suggestion.title })
  }
  return suggestion.title
}

function suggestionReason(suggestion: { kind: string; reason: string; payload: Record<string, unknown> }): string {
  if (suggestion.kind === 'study_pairs') {
    return t('catalog.suggestionStudyReason', {
      id: String(suggestion.payload.pdbId ?? ''),
      receptors: Number(suggestion.payload.receptorCount ?? 0),
      ligands: Number(suggestion.payload.ligandCount ?? 0),
    })
  }
  if (suggestion.kind === 'role') return t('catalog.suggestionRoleReason')
  if (suggestion.kind === 'duplicates') return t('catalog.suggestionDuplicatesReason')
  if (suggestion.kind === 'prepare') return t('catalog.suggestionPrepareReason')
  return suggestion.reason
}

async function addTag(): Promise<void> {
  const mol = active.value
  const tag = tagInput.value.trim()
  if (!mol || !tag || mol.tags.includes(tag)) return
  await store.patchMolecule(mol.id, { tags: [...mol.tags, tag] })
  tagInput.value = ''
}

async function removeTag(tag: string): Promise<void> {
  const mol = active.value
  if (!mol) return
  await store.patchMolecule(mol.id, { tags: mol.tags.filter((item) => item !== tag) })
}

async function addAlias(): Promise<void> {
  const mol = active.value
  const alias = aliasInput.value.trim()
  if (!mol || !alias || mol.aliases.includes(alias)) return
  await store.patchMolecule(mol.id, { aliases: [...mol.aliases, alias] })
  aliasInput.value = ''
}

async function removeAlias(alias: string): Promise<void> {
  const mol = active.value
  if (!mol) return
  await store.patchMolecule(mol.id, { aliases: mol.aliases.filter((item) => item !== alias) })
}

function openCollection(collection: { id: string; name: string }): void {
  void store.setScope({ kind: 'collection', id: collection.id, name: collection.name })
}

function collectionNodes(): { collection: (typeof store.collections)[number]; depth: number }[] {
  const byParent = new Map<string | null, typeof store.collections>()
  for (const collection of store.collections) {
    const key = collection.parentId ?? null
    const list = byParent.get(key) ?? []
    list.push(collection)
    byParent.set(key, list)
  }
  const result: { collection: (typeof store.collections)[number]; depth: number }[] = []
  function walk(parent: string | null, depth: number): void {
    for (const collection of byParent.get(parent) ?? []) {
      result.push({ collection, depth })
      walk(collection.id, depth + 1)
    }
  }
  walk(null, 0)
  return result
}


async function useForDocking(): Promise<void> {
  if (store.scope.kind !== 'study') return
  try {
    await store.useStudyForDocking(store.scope.id)
    await router.push('/docking')
    ElMessage.success(t('catalog.dockingReady'))
  } catch (cause) {
    ElMessage.error(cause instanceof Error ? cause.message : t('catalog.needPrepared'))
  }
}

async function assignSuggestionRole(suggestion: { moleculeIds: string[] }, role: 'receptor' | 'ligand'): Promise<void> {
  const id = suggestion.moleculeIds[0]
  if (!id) return
  try {
    await store.patchMolecule(id, { kindHint: role })
    await store.refresh()
    ElMessage.success(t('catalog.created'))
  } catch (cause) {
    ElMessage.error(cause instanceof Error ? cause.message : String(cause))
  }
}

async function prepareSuggestion(suggestion: { moleculeIds: string[] }): Promise<void> {
  const id = suggestion.moleculeIds[0]
  if (!id) return
  try {
    await store.prepareMolecule(id, { receptorOptions: defaultReceptorOptions() })
    await store.refresh()
    ElMessage.success(t('catalog.prepared'))
  } catch (cause) {
    ElMessage.error(cause instanceof Error ? cause.message : String(cause))
  }
}

async function applySuggestion(id: string): Promise<void> {
  const suggestion = store.suggestions.find((item) => item.id === id)
  if (!suggestion) return
  try {
    await store.applySuggestion(suggestion)
    ElMessage.success(t('catalog.created'))
  } catch (cause) {
    ElMessage.error(cause instanceof Error ? cause.message : String(cause))
  }
}
</script>

<template>
  <div class="catalog-page">
    <header class="catalog-head">
      <div class="catalog-head__intro">
        <h1>{{ t('catalog.title') }}</h1>
        <p>{{ t('catalog.subtitle') }} <span class="catalog-scope-sep">/</span> {{ scopeLabel() }}</p>
      </div>
      <div class="catalog-head__actions">
        <el-input
          v-model="store.query"
          class="catalog-search"
          size="small"
          clearable
          :prefix-icon="Search"
          :placeholder="t('catalog.searchPlaceholder')"
          @keyup.enter="store.search(true)"
          @clear="store.search(true)"
        />
        <el-button size="small" @click="store.search(true)">{{ t('catalog.search') }}</el-button>
        <el-button type="primary" size="small" :icon="Upload" :loading="importing" @click="importMolecules">
          {{ t('catalog.import') }}
        </el-button>
        <el-dropdown trigger="click" @command="handleCatalogCommand">
          <el-button size="small" :icon="MoreFilled">{{ t('catalog.more') }}</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="suggestions">
                {{ t('catalog.suggestions') }} ({{ store.suggestions.length }})
              </el-dropdown-item>
              <el-dropdown-item command="smiles">{{ t('catalog.fromSmiles') }}</el-dropdown-item>
              <el-dropdown-item command="draw">{{ t('molecules.drawButton') }}</el-dropdown-item>
              <el-dropdown-item command="library">{{ t('catalog.fromLibrary') }}</el-dropdown-item>
              <el-dropdown-item command="saveView">{{ t('catalog.saveView') }}</el-dropdown-item>
              <el-dropdown-item v-if="samples.length > 0" disabled>{{ t('catalog.samples') }}</el-dropdown-item>
              <el-dropdown-item
                v-for="sample in samples"
                :key="sample.path"
                :command="`sample:${sample.path}`"
              >{{ sample.name }}</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-popover trigger="click" :width="190">
          <template #reference>
            <el-button size="small">{{ t('catalog.columns') }}</el-button>
          </template>
          <div class="column-picker">
            <el-checkbox
              v-for="key in CATALOG_COLUMNS"
              :key="key"
              :model-value="columnVisible(key)"
              @update:model-value="toggleColumn(key)"
            >{{ columnLabel(key) }}</el-checkbox>
            <el-button text size="small" @click="resetColumns">{{ t('catalog.resetColumns') }}</el-button>
          </div>
        </el-popover>
      </div>
    </header>

    <div class="catalog-toolbar">
      <div class="catalog-toolbar__left">
        <el-popover
          v-if="hasFacets || activeFilterCount > 0"
          trigger="click"
          :width="560"
          placement="bottom-start"
          popper-class="catalog-filter-popper"
        >
          <template #reference>
            <el-button size="small" class="catalog-filter-trigger" :class="{ 'is-active': activeFilterCount > 0 }">
              {{ t('catalog.filters') }}
              <span v-if="activeFilterCount > 0" class="catalog-filter-count">{{ activeFilterCount }}</span>
            </el-button>
          </template>
          <div class="catalog-facets">
            <div v-if="store.facets.source.length" class="facet-group">
              <span class="facet-label">{{ t('catalog.facetSource') }}</span>
              <button
                v-for="item in store.facets.source"
                :key="`s-${item.value}`"
                type="button"
                class="facet-chip"
                :class="{ active: store.sourceFilter === item.value }"
                @click="store.toggleFacet('source', item.value)"
              >{{ item.value }} <small>{{ item.count }}</small></button>
            </div>
            <div v-if="store.facets.status.length" class="facet-group">
              <span class="facet-label">{{ t('catalog.facetStatus') }}</span>
              <button
                v-for="item in store.facets.status"
                :key="`st-${item.value}`"
                type="button"
                class="facet-chip"
                :class="{ active: store.status === item.value }"
                @click="store.toggleFacet('status', item.value)"
              >{{ item.value }} <small>{{ item.count }}</small></button>
            </div>
            <div v-if="readableTagFacets.length" class="facet-group facet-group--tags">
              <span class="facet-label">{{ t('catalog.facetTags') }}</span>
              <button
                v-for="item in visibleTagFacets"
                :key="`t-${item.value}`"
                type="button"
                class="facet-chip"
                :class="{ active: store.tagFilter === item.value }"
                @click="store.toggleFacet('tag', item.value)"
              >#{{ item.value }} <small>{{ item.count }}</small></button>
              <ElPopover v-if="hiddenTagFacets.length" trigger="click" :width="260">
                <template #reference>
                  <button type="button" class="facet-chip facet-chip--more">
                    +{{ hiddenTagFacets.length }} {{ t('catalog.moreTags') }}
                  </button>
                </template>
                <div class="facet-more">
                  <el-input
                    v-model="tagFacetQuery"
                    size="small"
                    clearable
                    :placeholder="t('catalog.filterTags')"
                  />
                  <div class="facet-more__list">
                    <button
                      v-for="item in filteredHiddenTags"
                      :key="`m-${item.value}`"
                      type="button"
                      class="facet-chip"
                      :class="{ active: store.tagFilter === item.value }"
                      @click="store.toggleFacet('tag', item.value)"
                    >#{{ item.value }} <small>{{ item.count }}</small></button>
                    <span v-if="filteredHiddenTags.length === 0" class="facet-empty">
                      {{ t('catalog.noMatchingTags') }}
                    </span>
                  </div>
                </div>
              </ElPopover>
            </div>
            <button
              v-if="activeFilterCount > 0"
              type="button"
              class="facet-chip facet-chip--clear"
              @click="store.clearFacets()"
            >{{ t('catalog.clearFacets') }}</button>
          </div>
        </el-popover>
      </div>
      <div class="catalog-toolbar__right">
        <span class="catalog-result-count">{{ t('catalog.total', { n: store.total }) }}</span>
        <el-select :model-value="store.sort" size="small" style="width: 118px" @change="store.setSort">
          <el-option :label="t('catalog.sortUpdated')" value="updated" />
          <el-option :label="t('catalog.sortName')" value="name" />
          <el-option :label="t('catalog.sortWeight')" value="weight" />
        </el-select>
        <el-select :model-value="store.limit" size="small" style="width: 82px" @change="store.setPageSize">
          <el-option :label="'50'" :value="50" />
          <el-option :label="'100'" :value="100" />
          <el-option :label="'200'" :value="200" />
        </el-select>
      </div>
    </div>


    <div class="catalog-body">
      <aside class="catalog-tree">
        <button class="tree-item" :class="{ active: store.scope.kind === 'all' }" @click="store.setScope({ kind: 'all' })">
          {{ t('catalog.all') }} <span>{{ store.summary.molecules }}</span>
        </button>
        <button
          class="tree-item"
          :class="{ active: store.scope.kind === 'unassigned' }"
          @click="store.setScope({ kind: 'unassigned' })"
        >
          {{ t('catalog.unassigned') }}
        </button>

        <section class="tree-section">
          <div class="tree-section__head">
            <span>{{ t('catalog.studies') }}</span>
            <button type="button" @click="createStudy">＋</button>
          </div>
          <div v-for="study in store.studies" :key="study.id" class="tree-row">
            <button
              class="tree-item tree-item--child"
              :class="{ active: store.scope.kind === 'study' && store.scope.id === study.id }"
              @click="store.setScope({ kind: 'study', id: study.id, name: study.name })"
            >
              <span>{{ study.name }}</span>
              <small>{{ study.receptorCount }}R · {{ study.ligandCount }}L</small>
            </button>
            <button class="tree-delete" :title="t('common.delete')" @click.stop="removeStudy(study.id, study.name)">×</button>
          </div>
        </section>

        <section class="tree-section">
          <div class="tree-section__head">
            <span>{{ t('catalog.collections') }}</span>
            <button type="button" @click="createCollection">＋</button>
          </div>
          <div v-for="node in collectionNodes()" :key="node.collection.id" class="tree-row">
            <button
              class="tree-item tree-item--child"
              :class="{ active: store.scope.kind === 'collection' && store.scope.id === node.collection.id }"
              :style="{ paddingLeft: `${16 + node.depth * 12}px` }"
              @click="store.setScope({ kind: 'collection', id: node.collection.id, name: node.collection.name })"
            >
              <span>{{ node.collection.name }}</span>
              <small>{{ node.collection.moleculeCount }}</small>
            </button>
            <button class="tree-delete" :title="t('common.delete')" @click.stop="removeCollection(node.collection.id, node.collection.name)">×</button>
          </div>
        </section>

        <section class="tree-section">
          <div class="tree-section__head">
            <span>{{ t('catalog.libraries') }}</span>
            <button type="button" @click="createLibrary">＋</button>
          </div>
          <div v-for="library in store.libraries" :key="library.id" class="tree-row">
            <button
              class="tree-item tree-item--child"
              :class="{ active: store.scope.kind === 'library' && store.scope.id === library.id }"
              @click="store.setScope({ kind: 'library', id: library.id, name: library.name })"
            >
              <span>{{ library.name }}</span>
              <small>{{ library.moleculeCount }}</small>
            </button>
            <button class="tree-delete" :title="t('common.delete')" @click.stop="removeLibrary(library.id, library.name)">×</button>
          </div>
        </section>

        <section v-if="store.savedViews.length > 0" class="tree-section">
          <div class="tree-section__head"><span>{{ t('catalog.savedViews') }}</span></div>
          <div v-for="view in store.savedViews" :key="view.id" class="tree-row">
            <button class="tree-item tree-item--child" @click="applyView(view.id)">{{ view.name }}</button>
            <button class="tree-delete" :title="t('common.delete')" @click.stop="removeView(view.id)">×</button>
          </div>
        </section>
      </aside>

      <main class="catalog-main">
        <section v-if="store.scope.kind !== 'all' && store.scope.kind !== 'unassigned'" class="catalog-scope">
          <div class="catalog-scope__head">
            <div>
              <h2>{{ scopeLabel() }}</h2>
              <p v-if="store.scopeDetail && 'description' in store.scopeDetail">
                {{ store.scopeDetail.description || t('catalog.noDescription') }}
              </p>
            </div>
            <div class="catalog-scope__actions">
              <el-button size="small" @click="renameScope">{{ t('catalog.rename') }}</el-button>
              <el-button
                v-if="store.scope.kind === 'study'"
                size="small"
                type="primary"
                @click="useForDocking"
              >{{ t('catalog.useForDocking') }}</el-button>
            </div>
          </div>
          <div v-if="store.scope.kind === 'study'" class="catalog-members">
            <div v-for="member in studyMembers" :key="`${member.id}-${member.role}`" class="catalog-member">
              <span class="catalog-member__role">{{ member.role }}</span>
              <span>{{ member.name }}</span>
              <span v-if="member.isPrimary" class="catalog-member__primary">{{ t('catalog.primary') }}</span>
              <button
                v-else-if="member.role === 'receptor'"
                type="button"
                class="catalog-member__link"
                @click="store.setStudyPrimary(member.id)"
              >{{ t('catalog.makePrimary') }}</button>
              <button type="button" class="tree-delete" @click="removeScopeMember(member.id, member.role)">×</button>
            </div>
          </div>
          <div v-else-if="store.scope.kind === 'library'" class="catalog-scope-summary">
            <span>{{ t('catalog.collectionMembers', { n: libraryMembers.length }) }}</span>
            <span class="muted">
              {{ t('catalog.libraryPrepared', {
                prepared: libraryPreparedCount,
                total: libraryMembers.length,
              }) }}
            </span>
            <span class="muted">{{ t('catalog.scopeMembersHint') }}</span>
          </div>
          <div v-else-if="store.scope.kind === 'collection'" class="catalog-scope-summary">
            <span>{{ t('catalog.collectionMembers', { n: collectionCount }) }}</span>
            <span class="muted">{{ t('catalog.scopeMembersHint') }}</span>
          </div>
        </section>
        <div v-if="selectedCount > 0" class="catalog-bulk">
          <strong>{{ t('catalog.selected', { n: selectedCount }) }}</strong>
          <el-select v-model="targetStudyId" size="small" clearable :placeholder="t('catalog.addToStudy')">
            <el-option v-for="study in store.studies" :key="study.id" :label="study.name" :value="study.id" />
          </el-select>
          <el-button size="small" :disabled="!targetStudyId" @click="addToStudy">{{ t('catalog.add') }}</el-button>
          <el-select v-model="targetCollectionId" size="small" clearable :placeholder="t('catalog.addToCollection')">
            <el-option
              v-for="collection in store.collections"
              :key="collection.id"
              :label="collection.name"
              :value="collection.id"
            />
          </el-select>
          <el-button size="small" :disabled="!targetCollectionId" @click="addToCollection">{{ t('catalog.add') }}</el-button>
          <el-button size="small" @click="createStudy">{{ t('catalog.createStudy') }}</el-button>
          <el-button size="small" @click="createLibrary">{{ t('catalog.createLibrary') }}</el-button>
          <el-input v-model="bulkTagInput" size="small" style="width: 120px" :placeholder="t('catalog.addTag')" @keyup.enter="addBulkTag" />
          <el-button size="small" :disabled="!bulkTagInput.trim()" @click="addBulkTag">{{ t('catalog.tag') }}</el-button>
          <el-button size="small" text @click="store.clearSelection()">{{ t('catalog.clearSelection') }}</el-button>
        </div>

        <el-alert v-if="store.error" type="error" :title="store.error" :closable="false" show-icon />

        <div v-loading="store.loading" class="catalog-table-wrap">
          <el-auto-resizer>
            <template #default="{ width, height }">
              <el-table-v2
                :columns="tableColumns"
                :data="store.molecules"
                :width="width"
                :height="height"
                :row-height="48"
                row-key="id"
                :row-class="rowClass"
                :row-event-handlers="tableRowEvents"
              />
            </template>
          </el-auto-resizer>
          <el-empty
            v-if="!store.loading && store.molecules.length === 0"
            :description="t('catalog.noMatches')"
            class="catalog-empty"
          />
        </div>

        <footer class="catalog-pager">
          <span>{{ t('catalog.total', { n: store.total }) }}</span>
          <el-button v-if="store.total > 0" size="small" @click="store.selectAllMatching()">
            {{ t('catalog.selectAllMatching') }}
          </el-button>
          <el-button size="small" :disabled="store.offset === 0" @click="store.previousPage()">‹</el-button>
          <span>{{ store.page }} / {{ store.pages }}</span>
          <el-button size="small" :disabled="store.offset + store.limit >= store.total" @click="store.nextPage()">›</el-button>
        </footer>
      </main>

      <aside class="catalog-detail">
        <template v-if="active">
          <h2>{{ active.name }}</h2>
          <p v-if="chineseAlias(active.aliases)" class="catalog-detail__zh">
            {{ chineseAlias(active.aliases) }}
          </p>
          <p class="muted">{{ kindLabel(active.kindHint) }} · {{ active.source || t('catalog.local') }}</p>
          <el-button
            v-if="active.prepStatus !== 'prepared'"
            size="small"
            @click="prepareOpen = true"
          >
            {{ t('catalog.prepare') }}
          </el-button>
          <el-button size="small" text type="danger" @click="removeActive">{{ t('catalog.removeMolecule') }}</el-button>
          <ViewportCanvas
            v-if="receptorUrl || ligandUrl"
            :receptor-url="receptorUrl"
            :ligand-url="ligandUrl"
            class="catalog-detail__view"
          />
          <template v-if="isReceptor">
          <dl class="catalog-receptor-facts">
            <template v-for="row in receptorRows" :key="row.label">
              <dt>{{ row.label }}</dt>
              <dd>
                <a v-if="row.href" :href="row.href" target="_blank" rel="noreferrer">{{ row.value }}</a>
                <span v-else>{{ row.value }}</span>
              </dd>
            </template>
            <dt>{{ t('catalog.identity') }}</dt><dd><code>{{ active.identityKey }}</code></dd>
            <dt>{{ t('catalog.study') }}</dt>
            <dd>{{ active.studies.map((item: { name: string; role: string }) => `${item.name} (${item.role})`).join(', ') || '—' }}</dd>
            <dt>{{ t('catalog.tags') }}</dt>
            <dd>
              <el-tag
                v-for="tag in active.tags"
                :key="tag"
                size="small"
                effect="plain"
                closable
                @close="removeTag(tag)"
              >{{ tag }}</el-tag>
              <div class="tag-input">
                <el-input v-model="tagInput" size="small" :placeholder="t('catalog.addTag')" @keyup.enter="addTag" />
                <el-button size="small" @click="addTag">{{ t('catalog.add') }}</el-button>
              </div>
            </dd>
          </dl>
          <p v-if="isReceptor && active.molecularWeight" class="catalog-receptor-note catalog-receptor-note--muted">
            {{ t('catalog.proteinMassNote') }}
          </p>
          <p v-if="receptorNote" class="catalog-receptor-note">
            <strong>{{ t('catalog.constructNote') }}:</strong> {{ receptorNote }}
          </p>
          </template>
          <dl v-else>
            <dt>{{ t('catalog.identity') }}</dt><dd><code>{{ active.identityKey }}</code></dd>
            <dt>{{ t('catalog.formula') }}</dt><dd>{{ active.formula || '—' }}</dd>
            <dt>{{ t('catalog.mw') }}</dt><dd>{{ active.molecularWeight?.toFixed(2) ?? '—' }}</dd>
            <dt>{{ t('catalog.smiles') }}</dt>
            <dd class="catalog-smiles">
              <code :title="active.canonicalSmiles || ''">{{ active.canonicalSmiles || '—' }}</code>
              <el-button
                v-if="active.canonicalSmiles"
                text
                size="small"
                :icon="CopyDocument"
                :title="t('common.copy')"
                @click="copySmiles"
              />
            </dd>
            <dt>{{ t('catalog.study') }}</dt>
            <dd>{{ active.studies.map((item: { name: string; role: string }) => `${item.name} (${item.role})`).join(', ') || '—' }}</dd>
            <dt>{{ t('catalog.tags') }}</dt>
            <dd>
              <el-tag
                v-for="tag in active.tags"
                :key="tag"
                size="small"
                effect="plain"
                closable
                @close="removeTag(tag)"
              >{{ tag }}</el-tag>
              <div class="tag-input">
                <el-input v-model="tagInput" size="small" :placeholder="t('catalog.addTag')" @keyup.enter="addTag" />
                <el-button size="small" @click="addTag">{{ t('catalog.add') }}</el-button>
              </div>
            </dd>
          </dl>
          <section class="catalog-aliases">
            <h3>{{ t('molecules.aliases') }}</h3>
            <div class="catalog-alias-tags">
              <el-tag
                v-for="alias in active.aliases"
                :key="alias"
                size="small"
                effect="plain"
                closable
                @close="removeAlias(alias)"
              >{{ alias }}</el-tag>
              <span v-if="!active.aliases.length" class="muted">{{ t('common.none') }}</span>
            </div>
            <div class="tag-input">
              <el-input
                v-model="aliasInput"
                size="small"
                :placeholder="t('molecules.aliasPlaceholder')"
                @keyup.enter="addAlias"
              />
              <el-button size="small" @click="addAlias">{{ t('molecules.addAlias') }}</el-button>
            </div>
          </section>
          <section v-if="active.collections.length" class="catalog-collections">
            <h3>{{ t('catalog.collections') }}</h3>
            <div class="catalog-collection-links">
              <button
                v-for="collection in active.collections"
                :key="collection.id"
                type="button"
                :title="collection.name"
                @click="openCollection(collection)"
              >{{ collection.name }}</button>
            </div>
          </section>
          <h3>{{ t('catalog.files') }}</h3>
          <ul class="catalog-files">
            <li v-for="file in active.files" :key="`${file.kind}-${file.path}`">
              <span>{{ file.kind }}</span>
              <code>{{ file.path }}</code>
            </li>
          </ul>
        </template>
        <p v-else class="muted">{{ t('catalog.selectHint') }}</p>
      </aside>
    </div>

    <section v-if="showSuggestions" class="catalog-suggestions">
      <h3>{{ t('catalog.suggestions') }}</h3>
      <p v-if="store.suggestions.length === 0" class="muted">{{ t('catalog.noSuggestions') }}</p>
      <article v-for="suggestion in store.suggestions" :key="suggestion.id" class="catalog-suggestion">
        <div>
          <strong>{{ suggestionTitle(suggestion) }}</strong>
          <span class="confidence">{{ Math.round(suggestion.confidence * 100) }}%</span>
          <p>{{ suggestionReason(suggestion) }}</p>
        </div>
        <div class="suggestion-actions">
          <el-button v-if="suggestion.kind === 'study_pairs'" size="small" @click="applySuggestion(suggestion.id)">
            {{ t('catalog.apply') }}
          </el-button>
          <template v-if="suggestion.kind === 'role'">
            <el-button size="small" @click="assignSuggestionRole(suggestion, 'receptor')">
              {{ t('molecules.typeReceptor') }}
            </el-button>
            <el-button size="small" @click="assignSuggestionRole(suggestion, 'ligand')">
              {{ t('molecules.typeLigand') }}
            </el-button>
          </template>
          <el-button v-if="suggestion.kind === 'prepare'" size="small" @click="prepareSuggestion(suggestion)">
            {{ t('catalog.prepare') }}
          </el-button>
        </div>
      </article>
    </section>
    <CatalogPrepareDialog v-model="prepareOpen" :molecule="active" />

    <ElDialog v-model="smilesOpen" :title="t('catalog.fromSmiles')" width="520px">
      <p class="muted">{{ t('catalog.smilesHint') }}</p>
      <ElInput v-model="smilesText" type="textarea" :rows="7" :placeholder="t('molecules.smilesPlaceholder')" />
      <ElInput v-model="smilesName" class="smiles-name" :placeholder="t('catalog.smilesName')" />
      <template #footer>
        <ElButton @click="smilesOpen = false">{{ t('common.cancel') }}</ElButton>
        <ElButton type="primary" :loading="smilesBusy" @click="submitSmiles">{{ t('catalog.smilesSubmit') }}</ElButton>
      </template>
    </ElDialog>

    <MoleculeLibraryDialog ref="libraryDialog" catalog-mode @paths="importPaths" />
    <SketcherDialog ref="sketcher" catalog-mode @smiles="onSketched" />
  </div>
</template>

<style scoped>
.catalog-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  gap: 10px;
  padding: 14px 16px;
}
.catalog-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}
.catalog-head h1 { margin: 0; font-size: 20px; }
.catalog-head p { margin: 3px 0 0; color: var(--vs-text-faint); font-size: 12px; }
.catalog-head__actions { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.catalog-search { width: 300px; }
.catalog-body {
  display: grid;
  grid-template-columns: 210px minmax(0, 1fr) 300px;
  gap: 12px;
  min-height: 0;
  flex: 1;
}
.catalog-tree {
  min-height: 0;
  overflow: auto;
  border: 1px solid var(--vs-border);
  border-radius: var(--vs-radius);
  background: var(--vs-bg-surface);
  padding: 8px;
}
.tree-item {
  display: flex;
  width: 100%;
  justify-content: space-between;
  gap: 8px;
  border: 0;
  border-radius: var(--vs-radius-sm);
  padding: 5px 8px;
  background: transparent;
  color: var(--vs-text);
  font: inherit;
  font-size: 12px;
  text-align: left;
  cursor: pointer;
}
.tree-item:hover, .tree-item.active { background: var(--vs-accent-soft); color: var(--vs-accent); }
.tree-item--child { padding-left: 16px; font-size: 11.5px; }
.tree-row { display: flex; align-items: center; }
.tree-row .tree-item { flex: 1; min-width: 0; }
.tree-delete { border: 0; background: transparent; color: var(--vs-text-faint); cursor: pointer; padding: 2px 4px; }
.tree-delete:hover { color: var(--vs-danger); }
.tree-section { margin-top: 10px; }
.tree-section__head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 4px 6px;
  color: var(--vs-text-faint);
  font-size: 11px;
  text-transform: uppercase;
}
.tree-section__head button { border: 0; background: transparent; color: var(--vs-accent); cursor: pointer; }
.catalog-main { display: flex; flex-direction: column; min-height: 0; gap: 8px; }
.catalog-scope {
  border: 1px solid var(--vs-border);
  border-radius: var(--vs-radius);
  background: var(--vs-bg-surface);
  padding: 8px 10px;
}
.catalog-scope__head { display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; }
.catalog-scope__head h2 { margin: 0; font-size: 15px; }
.catalog-scope__head p { margin: 2px 0 0; color: var(--vs-text-faint); font-size: 11.5px; }
.catalog-scope__actions { display: flex; gap: 4px; }
.catalog-members { display: flex; flex-wrap: wrap; gap: 4px 12px; margin-top: 6px; }
.catalog-member { display: flex; align-items: center; gap: 5px; font-size: 11.5px; }
.catalog-member__role { color: var(--vs-accent); font-family: var(--vs-font-mono); }
.catalog-member__primary { color: var(--vs-warning); }
.catalog-member__link { border: 0; background: transparent; color: var(--vs-accent); cursor: pointer; font-size: 11px; }
.catalog-bulk {
  display: flex;
  gap: 6px;
  align-items: center;
  flex-wrap: wrap;
  padding: 6px 8px;
  border: 1px solid var(--vs-border);
  border-radius: var(--vs-radius);
  background: var(--vs-bg-surface);
  font-size: 12px;
}
.column-picker { display: flex; flex-direction: column; gap: 2px; }
.column-picker :deep(.el-checkbox) { height: 24px; }
.catalog-facets { display: flex; flex-wrap: wrap; gap: 6px 14px; align-items: center; }
.facet-group { display: flex; flex-wrap: wrap; gap: 4px; align-items: center; min-width: 0; }
.facet-label { color: var(--vs-text-faint); font-size: 10px; letter-spacing: .04em; }
.facet-group--tags { flex: 1 1 260px; }
.facet-chip--more { border-style: dashed; }
.facet-more { display: flex; flex-direction: column; gap: 8px; }
.facet-more__list { display: flex; flex-wrap: wrap; gap: 4px; max-height: 240px; overflow: auto; }
.facet-empty { font-size: 12px; color: var(--vs-text-faint); }
.facet-chip { border: 1px solid var(--vs-border); border-radius: 999px; background: transparent; color: var(--vs-text-muted); padding: 1px 7px; font-size: 11px; cursor: pointer; }
.facet-chip.active { border-color: var(--vs-accent); color: var(--vs-accent); background: var(--vs-accent-soft); }
.facet-chip small { opacity: 0.7; }
.facet-chip--clear { color: var(--vs-danger); }
.catalog-scope-summary { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; font-size: 12px; }
.catalog-table-wrap { position: relative; flex: 1; min-height: 160px; border: 1px solid var(--vs-border); border-radius: var(--vs-radius); overflow: hidden; }
:deep(.catalog-name-cell) { display: flex; flex-direction: column; min-width: 0; line-height: 1.2; }
:deep(.catalog-name-zh) { overflow: hidden; color: var(--vs-text-muted); font-size: 10.5px; text-overflow: ellipsis; white-space: nowrap; }
:deep(.catalog-name-link) { border: 0; background: transparent; color: inherit; padding: 0; font: inherit; text-align: left; cursor: pointer; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 100%; }
.catalog-name-link:hover { color: var(--vs-accent); text-decoration: underline; }
:deep(.catalog-tag-cell) { display: inline-flex; gap: 3px; max-width: 100%; overflow: hidden; flex-wrap: nowrap; white-space: nowrap; }
:deep(.catalog-tag) { max-width: 150px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; border: 1px solid var(--vs-border); border-radius: 999px; padding: 0 5px; font-size: 10px; }
.catalog-pager { display: flex; align-items: center; justify-content: flex-end; gap: 8px; font-size: 12px; color: var(--vs-text-muted); }
.catalog-detail {
  min-height: 0;
  overflow: auto;
  border: 1px solid var(--vs-border);
  border-radius: var(--vs-radius);
  background: var(--vs-bg-surface);
  padding: 12px;
}
.catalog-detail h2 { margin: 0 0 2px; font-size: 15px; }
.catalog-detail__zh { margin: 0 0 2px; color: var(--vs-text-muted); font-size: 12px; }
.catalog-receptor-facts dd a { color: var(--vs-accent); text-decoration: none; }
.catalog-receptor-facts dd a:hover { text-decoration: underline; }
.catalog-receptor-note { margin: 8px 0; padding: 7px 8px; border-left: 2px solid var(--vs-accent); background: var(--vs-bg-sunken); color: var(--vs-text-muted); font-size: 11px; line-height: 1.5; }
.catalog-receptor-note--muted { border-left-color: var(--vs-border); }
.catalog-detail__view { height: 180px; margin: 8px 0; }
.catalog-detail dl { display: grid; grid-template-columns: 82px 1fr; gap: 4px 8px; font-size: 11.5px; }
.catalog-detail dt { color: var(--vs-text-faint); }
.catalog-detail dd { margin: 0; overflow-wrap: anywhere; }
.catalog-empty { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; pointer-events: none; }
.catalog-aliases { margin-top: 8px; }
.catalog-aliases h3 { margin: 8px 0 5px; font-size: 12px; }
.catalog-alias-tags { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 4px; }
.catalog-collections h3 { margin: 10px 0 5px; font-size: 12px; }
.catalog-collection-links { display: flex; flex-wrap: wrap; gap: 4px; }
.catalog-collection-links button {
  max-width: 100%;
  overflow: hidden;
  border: 1px solid var(--vs-border);
  border-radius: 999px;
  background: transparent;
  color: var(--vs-text-muted);
  padding: 2px 8px;
  font: inherit;
  font-size: 10.5px;
  text-overflow: ellipsis;
  white-space: nowrap;
  cursor: pointer;
}
.catalog-collection-links button:hover { border-color: var(--vs-accent); color: var(--vs-accent); }
.catalog-files { list-style: none; padding: 0; margin: 0; font-size: 11px; }
.catalog-files li { display: flex; gap: 6px; padding: 3px 0; overflow-wrap: anywhere; }
.catalog-files span { color: var(--vs-accent); flex: 0 0 auto; }
.catalog-suggestions {
  max-height: 220px;
  overflow: auto;
  border: 1px solid var(--vs-border);
  border-radius: var(--vs-radius);
  background: var(--vs-bg-surface);
  padding: 8px 12px;
}
.catalog-suggestions h3 { margin: 0 0 6px; font-size: 13px; }
.catalog-suggestion { display: flex; justify-content: space-between; gap: 12px; padding: 6px 0; border-top: 1px solid var(--vs-border); font-size: 12px; }
.catalog-suggestion p { margin: 2px 0 0; color: var(--vs-text-muted); }
.suggestion-actions { display: flex; gap: 4px; align-items: center; }
.confidence { margin-left: 8px; color: var(--vs-warning); font-size: 11px; }
.muted { color: var(--vs-text-faint); font-size: 12px; }
.smiles-name { margin-top: 8px; }
.break { word-break: break-all; }
.tag-input { display: flex; gap: 4px; margin-top: 4px; }
:deep(.catalog-row--active) { background: var(--vs-accent-soft); }

/* Catalog workbench header: one primary action lane, one tool lane, filters
   on demand.  The table stays the focal point rather than the controls. */
.catalog-page { gap: 0; padding: 18px 20px 14px; }
.catalog-head {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: end;
  gap: 20px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--vs-border);
}
.catalog-head__intro { min-width: 0; }
.catalog-head h1 {
  margin: 0;
  font-size: 22px;
  font-weight: 650;
  letter-spacing: -0.025em;
  line-height: 1.15;
}
.catalog-head p { margin: 5px 0 0; color: var(--vs-text-muted); font-size: 12.5px; }
.catalog-scope-sep { padding: 0 7px; color: var(--vs-border-strong); }
.catalog-head__actions { display: flex; align-items: center; justify-content: flex-end; gap: 8px; flex-wrap: nowrap; }
.catalog-head__actions :deep(.el-button + .el-button) { margin-left: 0; }
.catalog-search { width: clamp(220px, 28vw, 360px); }
.catalog-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 10px 0 12px;
}
.catalog-toolbar__left, .catalog-toolbar__right { display: flex; align-items: center; gap: 8px; min-width: 0; }
.catalog-result-count { color: var(--vs-text-faint); font-size: 11.5px; white-space: nowrap; }
.catalog-filter-trigger { color: var(--vs-text-muted); }
.catalog-filter-trigger.is-active { border-color: var(--vs-accent); color: var(--vs-accent); background: var(--vs-accent-soft); }
.catalog-filter-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 17px;
  height: 17px;
  margin-left: 5px;
  border-radius: 999px;
  background: var(--vs-accent);
  color: var(--vs-bg-surface);
  font-size: 10px;
  line-height: 1;
}
:global(.catalog-filter-popper) { max-width: calc(100vw - 32px); }
:global(.catalog-filter-popper) .catalog-facets {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 12px;
}
:global(.catalog-filter-popper) .facet-group { align-items: flex-start; }
:global(.catalog-filter-popper) .facet-label { flex: 0 0 74px; padding-top: 3px; }
.catalog-body { gap: 14px; }
.catalog-tree, .catalog-detail { border-color: var(--vs-border); }
.catalog-detail { padding: 14px; }
.catalog-main { gap: 10px; }
.catalog-table-wrap { border-radius: var(--vs-radius); }
@media (max-width: 1180px) {
  .catalog-page { padding: 16px 14px 12px; }
  .catalog-head { grid-template-columns: 1fr; gap: 12px; align-items: start; }
  .catalog-head__actions { justify-content: flex-start; flex-wrap: wrap; }
  .catalog-search { flex: 1 1 260px; width: auto; }
  .catalog-body { grid-template-columns: 190px minmax(0, 1fr) 270px; gap: 10px; }
}
@media (max-width: 900px) {
  .catalog-body {
    grid-template-columns: 180px minmax(0, 1fr);
    grid-template-rows: minmax(0, 1fr) auto;
  }
  /* Keep the selected molecule's preview and prepare action reachable when
     the third column no longer fits; hiding it made selection a dead end. */
  .catalog-detail {
    display: block;
    grid-column: 1 / -1;
    max-height: 260px;
  }
  .catalog-result-count { display: none; }
}
@media (max-width: 620px) {
  .catalog-page { padding: 12px 10px 10px; }
  .catalog-head h1 { font-size: 19px; }
  .catalog-head__actions :deep(.el-button) { padding-inline: 9px; }
  .catalog-body { grid-template-columns: 1fr; }
  .catalog-tree { display: none; }
  .catalog-toolbar { flex-wrap: wrap; }
  .catalog-toolbar__right { width: 100%; justify-content: space-between; }
}
</style>
