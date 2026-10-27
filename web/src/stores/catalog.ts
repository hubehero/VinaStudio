import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { api } from '@/api/http'
import { useMoleculeStore } from '@/stores/molecules'
import type {
  CatalogCollection,
  CatalogPrepareOptions,
  CatalogLibrary,
  CatalogMolecule,
  CatalogSearchFacets,
  CatalogStudy,
  CatalogSavedView,
  CatalogSuggestion,
  CatalogSummary,
} from '@/types/api'

export type CatalogScope =
  | { kind: 'all' }
  | { kind: 'study'; id: string; name: string }
  | { kind: 'collection'; id: string; name: string }
  | { kind: 'library'; id: string; name: string }
  | { kind: 'unassigned' }

const EMPTY_FACETS: CatalogSearchFacets = { source: [], status: [], prep: [], tags: [] }

export const useCatalogStore = defineStore('catalog', () => {
  const molecules = ref<CatalogMolecule[]>([])
  const total = ref(0)
  const limit = ref(50)
  const sort = ref('updated')
  const offset = ref(0)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const query = ref('')
  const facets = ref<CatalogSearchFacets>({ ...EMPTY_FACETS })
  const studies = ref<CatalogStudy[]>([])
  const collections = ref<CatalogCollection[]>([])
  const libraries = ref<CatalogLibrary[]>([])
  const savedViews = ref<CatalogSavedView[]>([])
  const suggestions = ref<CatalogSuggestion[]>([])
  const summary = ref<CatalogSummary>({ molecules: 0, studies: 0, collections: 0, libraries: 0 })
  const scope = ref<CatalogScope>({ kind: 'all' })
  const kind = ref('')
  const status = ref('')
  const sourceFilter = ref('')
  const tagFilter = ref('')
  const selectedIds = ref<string[]>([])
  const activeId = ref<string | null>(null)
  let generation = 0

  const scopeDetail = ref<CatalogStudy | CatalogLibrary | CatalogCollection | null>(null)
  const scopeLoading = ref(false)

  const activeMolecule = computed(
    () => molecules.value.find((item) => item.id === activeId.value) ?? null,
  )
  const selectedMolecules = computed(() =>
    molecules.value.filter((item) => selectedIds.value.includes(item.id)),
  )
  const page = computed(() => Math.floor(offset.value / limit.value) + 1)
  const pages = computed(() => Math.max(1, Math.ceil(total.value / limit.value)))
  const allSelected = computed(
    () => molecules.value.length > 0 && molecules.value.every((item) => selectedIds.value.includes(item.id)),
  )

  async function loadScopeDetail(): Promise<void> {
    scopeLoading.value = true
    try {
      if (scope.value.kind === 'study') {
        scopeDetail.value = await api.catalogStudy(scope.value.id)
      } else if (scope.value.kind === 'library') {
        scopeDetail.value = await api.catalogLibrary(scope.value.id)
      } else if (scope.value.kind === 'collection') {
        scopeDetail.value = await api.catalogCollection(scope.value.id)
      } else {
        scopeDetail.value = null
      }
    } catch {
      scopeDetail.value = null
    } finally {
      scopeLoading.value = false
    }
  }

  async function setScope(next: CatalogScope): Promise<void> {
    scope.value = next
    selectedIds.value = []
    activeId.value = null
    scopeDetail.value = null
    // A scope is a new list, not a filter refinement of the previous one.
    // Keeping a hidden search/facet from another scope made a 125-member
    // collection render as an empty table.
    query.value = ''
    kind.value = ''
    status.value = ''
    sourceFilter.value = ''
    tagFilter.value = ''
    await Promise.all([loadScopeDetail(), search(true)])
  }

  function toggleSelected(id: string): void {
    selectedIds.value = selectedIds.value.includes(id)
      ? selectedIds.value.filter((item) => item !== id)
      : [...selectedIds.value, id]
  }

  function selectAll(): void {
    selectedIds.value = allSelected.value ? [] : molecules.value.map((item) => item.id)
  }

  function selectMolecule(id: string | null): void {
    activeId.value = id
  }

  async function loadContext(): Promise<void> {
    const [nextSummary, nextStudies, nextCollections, nextLibraries, nextSuggestions, nextSavedViews] =
      await Promise.all([
        api.catalogSummary(),
        api.catalogStudies(),
        api.catalogCollections(),
        api.catalogLibraries(),
        api.catalogSuggestions(),
        api.catalogSavedViews(),
      ])
    summary.value = nextSummary
    studies.value = nextStudies
    collections.value = nextCollections
    libraries.value = nextLibraries
    suggestions.value = nextSuggestions
    savedViews.value = nextSavedViews
  }

  function searchParams(): Record<string, string | number | boolean | undefined> {
    const params: Record<string, string | number | boolean | undefined> = {
      q: query.value,
      limit: limit.value,
      offset: offset.value,
      sort: sort.value,
      kind: kind.value || undefined,
      status: status.value || undefined,
      source: sourceFilter.value || undefined,
      tag: tagFilter.value || undefined,
    }
    if (scope.value.kind === 'study') params.study_id = scope.value.id
    else if (scope.value.kind === 'collection') params.collection_id = scope.value.id
    else if (scope.value.kind === 'library') params.library_id = scope.value.id
    else if (scope.value.kind === 'unassigned') params.unassigned = true
    return params
  }

  async function search(reset = false): Promise<void> {
    if (reset) {
      offset.value = 0
      selectedIds.value = []
      activeId.value = null
    }
    const requestGeneration = ++generation
    loading.value = true
    error.value = null
    try {
      const result = await api.catalogSearch(searchParams())
      if (requestGeneration !== generation) return
      molecules.value = result.items
      total.value = result.total
      facets.value = result.facets
      if (activeId.value && !result.items.some((item) => item.id === activeId.value)) {
        activeId.value = result.items[0]?.id ?? null
      }
      if (!activeId.value) activeId.value = result.items[0]?.id ?? null
    } catch (cause) {
      if (requestGeneration === generation) {
        error.value = cause instanceof Error ? cause.message : String(cause)
      }
    } finally {
      if (requestGeneration === generation) loading.value = false
    }
  }

  async function refresh(): Promise<void> {
    await Promise.all([loadContext(), search(true)])
  }

  function setSort(value: string): void {
    sort.value = value
    void search(true)
  }

  function setPageSize(value: number): void {
    limit.value = value
    void search(true)
  }

  async function nextPage(): Promise<void> {
    if (offset.value + limit.value >= total.value) return
    offset.value += limit.value
    await search()
  }

  async function previousPage(): Promise<void> {
    if (offset.value === 0) return
    offset.value = Math.max(0, offset.value - limit.value)
    await search()
  }

  async function patchMolecule(id: string, body: Record<string, unknown>): Promise<void> {
    const updated = await api.catalogPatchMolecule(id, body)
    const index = molecules.value.findIndex((item) => item.id === id)
    if (index >= 0) molecules.value[index] = updated
  }

  async function deleteMolecule(id: string): Promise<void> {
    await api.catalogDeleteMolecule(id)
    await refresh()
  }

  async function selectedDetails(): Promise<CatalogMolecule[]> {
    if (selectedIds.value.length > 500) {
      throw new Error('Please narrow the selection to 500 molecules for this action')
    }
    return Promise.all(selectedIds.value.map((id) => api.catalogMolecule(id)))
  }

  async function selectAllMatching(): Promise<void> {
    const result = await api.catalogMoleculeIds(searchParams())
    selectedIds.value = result.ids
  }

  function clearSelection(): void {
    selectedIds.value = []
  }

  async function bulkTag(tag: string): Promise<void> {
    const value = tag.trim()
    if (!value || selectedIds.value.length === 0) return
    await api.catalogBulkTags(selectedIds.value, [value])
    await search()
    await loadContext()
  }

  async function prepareMolecule(id: string, options?: CatalogPrepareOptions): Promise<void> {
    const updated = await api.catalogPrepareMolecule(id, options)
    const index = molecules.value.findIndex((item) => item.id === id)
    if (index >= 0) molecules.value[index] = updated
  }

  async function createStudy(name: string): Promise<CatalogStudy> {
    const members = await selectedDetails()
    const study = await api.catalogCreateStudy({ name })
    for (const molecule of members) {
      const role = molecule.kindHint === 'receptor' ? 'receptor' : 'ligand'
      await api.catalogAddStudyMember(study.id, {
        moleculeId: molecule.id,
        role,
        isPrimary: role === 'receptor',
      })
    }
    await loadContext()
    return api.catalogStudy(study.id)
  }

  async function addSelectedToStudy(studyId: string): Promise<void> {
    const members = await selectedDetails()
    for (const molecule of members) {
      const role = molecule.kindHint === 'receptor' ? 'receptor' : 'ligand'
      await api.catalogAddStudyMember(studyId, { moleculeId: molecule.id, role })
    }
    await loadContext()
    await search()
  }

  async function deleteStudy(id: string): Promise<void> {
    await api.catalogDeleteStudy(id)
    await refresh()
  }

  async function deleteCollection(id: string): Promise<void> {
    await api.catalogDeleteCollection(id)
    await refresh()
  }

  async function deleteLibrary(id: string): Promise<void> {
    await api.catalogDeleteLibrary(id)
    await refresh()
  }

  async function createCollection(name: string, parentId?: string | null): Promise<CatalogCollection> {
    const collection = await api.catalogCreateCollection({ name, parentId: parentId ?? null })
    if (selectedIds.value.length > 0) {
      await api.catalogAddCollectionMembers(collection.id, selectedIds.value)
    }
    await loadContext()
    return collection
  }

  async function addSelectedToCollection(collectionId: string): Promise<void> {
    await api.catalogAddCollectionMembers(collectionId, selectedIds.value)
    await loadContext()
    await search()
  }

  async function createLibrary(name: string): Promise<CatalogLibrary> {
    const ids = (await selectedDetails())
      .filter((item) => item.kindHint !== 'receptor')
      .map((item) => item.id)
    const library = await api.catalogCreateLibrary({ name, moleculeIds: ids })
    await loadContext()
    return library
  }

  /** Adopt a Study's primary receptor and first ligand into the existing
   * docking pipeline. Both must already have prepared PDBQT artifacts.
   */
  async function useStudyForDocking(studyId: string): Promise<void> {
    const study = await api.catalogStudy(studyId)
    const primary = study.members.find((item) => item.role === 'receptor' && item.isPrimary)
      ?? study.members.find((item) => item.role === 'receptor')
    const ligand = study.members.find((item) => item.role === 'ligand')
    if (!primary || !ligand) throw new Error('Study needs a receptor and a ligand')
    const [receptorDetail, ligandDetail] = await Promise.all([
      api.catalogMolecule(primary.id),
      api.catalogMolecule(ligand.id),
    ])
    const receptor = useMoleculeStore().adoptCatalogMolecule(receptorDetail)
    const ligandItem = useMoleculeStore().adoptCatalogMolecule(ligandDetail)
    const receptorPrepared = receptor.artifacts.some((item) => item.kind === 'pdbqt')
    const ligandPrepared = ligandItem.artifacts.some((item) => item.kind === 'pdbqt')
    if (!receptorPrepared || !ligandPrepared) {
      throw new Error('Prepare both receptor and ligand before docking')
    }
    useMoleculeStore().setPipelineReceptor(receptor.id)
    useMoleculeStore().setPipelineLigand(ligandItem.id)
  }

  async function renameScope(name: string): Promise<void> {
    if (scope.value.kind === 'study') {
      await api.catalogPatchStudy(scope.value.id, { name })
    } else if (scope.value.kind === 'collection') {
      await api.catalogPatchCollection(scope.value.id, { name })
    } else if (scope.value.kind === 'library') {
      await api.catalogPatchLibrary(scope.value.id, { name })
    } else {
      return
    }
    scope.value = { ...scope.value, name }
    await refresh()
    await loadScopeDetail()
  }

  async function removeStudyMember(moleculeId: string, role: string): Promise<void> {
    if (scope.value.kind !== 'study') return
    await api.catalogRemoveStudyMember(scope.value.id, moleculeId, role)
    await search()
    await loadScopeDetail()
  }

  async function removeCollectionMember(moleculeId: string): Promise<void> {
    if (scope.value.kind !== 'collection') return
    await api.catalogRemoveCollectionMember(scope.value.id, moleculeId)
    await search()
    await loadScopeDetail()
  }

  async function setStudyPrimary(moleculeId: string): Promise<void> {
    if (scope.value.kind !== 'study') return
    await api.catalogSetStudyPrimary(scope.value.id, moleculeId)
    await loadScopeDetail()
  }

  async function removeLibraryMember(moleculeId: string): Promise<void> {
    if (scope.value.kind !== 'library') return
    await api.catalogRemoveLibraryMember(scope.value.id, moleculeId)
    await search()
    await loadScopeDetail()
  }

  async function applySuggestion(suggestion: CatalogSuggestion): Promise<void> {
    if (suggestion.kind === 'study_pairs') {
      const pdbId = String(suggestion.payload.pdbId ?? '')
      const study = await api.catalogCreateStudy({
        name: pdbId ? `${pdbId} study` : suggestion.title,
        pdbId: pdbId || undefined,
        source: 'suggestion',
      })
      for (const moleculeId of suggestion.moleculeIds) {
        const molecule = await api.catalogMolecule(moleculeId)
        const role = molecule.kindHint === 'receptor' ? 'receptor' : 'ligand'
        await api.catalogAddStudyMember(study.id, {
          moleculeId,
          role,
          isPrimary: role === 'receptor',
        })
      }
    }
    await refresh()
  }

  function toggleFacet(kind: 'source' | 'tag' | 'status', value: string): void {
    if (kind === 'source') sourceFilter.value = sourceFilter.value === value ? '' : value
    else if (kind === 'tag') tagFilter.value = tagFilter.value === value ? '' : value
    else status.value = status.value === value ? '' : value
    void search(true)
  }

  function clearFacets(): void {
    sourceFilter.value = ''
    tagFilter.value = ''
    status.value = ''
    void search(true)
  }

  async function saveCurrentView(name: string): Promise<void> {
    const savedScope = scope.value
    await api.catalogCreateSavedView({
      name,
      query: {
        q: query.value,
        scope: savedScope,
        kind: kind.value,
        status: status.value,
        source: sourceFilter.value,
        tag: tagFilter.value,
      },
    })
    await loadContext()
  }

  async function applySavedView(view: CatalogSavedView): Promise<void> {
    const savedScope = view.query.scope as CatalogScope | undefined
    query.value = String(view.query.q ?? '')
    kind.value = String(view.query.kind ?? '')
    status.value = String(view.query.status ?? '')
    sourceFilter.value = String(view.query.source ?? '')
    tagFilter.value = String(view.query.tag ?? '')
    if (savedScope && 'kind' in savedScope) scope.value = savedScope
    await search(true)
    await loadScopeDetail()
  }

  async function deleteSavedView(id: string): Promise<void> {
    await api.catalogDeleteSavedView(id)
    await loadContext()
  }

  function clearQuery(): void {
    query.value = ''
    void search(true)
  }

  return {
    molecules,
    total,
    limit,
    sort,
    offset,
    page,
    pages,
    loading,
    error,
    query,
    facets,
    studies,
    collections,
    libraries,
    savedViews,
    suggestions,
    summary,
    scope,
    kind,
    status,
    sourceFilter,
    tagFilter,
    toggleFacet,
    clearFacets,
    selectedIds,
    activeId,
    activeMolecule,
    scopeDetail,
    scopeLoading,
    selectedMolecules,
    allSelected,
    loadContext,
    search,
    refresh,
    nextPage,
    previousPage,
    setSort,
    setPageSize,
    setScope,
    toggleSelected,
    selectAll,
    selectMolecule,
    patchMolecule,
    prepareMolecule,
    deleteMolecule,
    bulkTag,
    selectAllMatching,
    clearSelection,
    createStudy,
    addSelectedToStudy,
    createCollection,
    deleteStudy,
    deleteCollection,
    deleteLibrary,
    renameScope,
    removeStudyMember,
    removeLibraryMember,
    removeCollectionMember,
    setStudyPrimary,
    addSelectedToCollection,
    createLibrary,
    applySuggestion,
    useStudyForDocking,
    clearQuery,
    saveCurrentView,
    applySavedView,
    deleteSavedView,
  }
})
