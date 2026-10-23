import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { desktopBridge } from '@/api/bridge'
import { i18n } from '@/i18n'
import { api } from '@/api/http'
import {
  DEFAULT_LIGAND_OPTIONS,
  DEFAULT_RECEPTOR_OPTIONS,
  describeFailure,
} from '@/stores/preparation-shared'
import type {
  FileFilters,
  LigandReport,
  LibraryFetchResponse,
  ReceptorReport,
  SampleFile,
} from '@/types/api'
import type {
  MoleculeGroup,
  MoleculeItem,
  MoleculeManifest,
  MoleculeManifestEntry,
  MoleculeStatus,
  MoleculeType,
} from '@/types/molecule'
import { useUndoStore } from '@/stores/undo'
import { getEffectiveType } from '@/types/molecule'

let nextId = 0
function generateId(): string {
  nextId += 1
  return `mol-${nextId}-${Date.now().toString(36)}`
}

/** Extensions that already say what the file is; the rest have to be read. */
function detectTypeByExtension(name: string): MoleculeType {
  const dot = name.lastIndexOf('.')
  if (dot === -1) return 'unknown'
  const ext = name.slice(dot).toLowerCase()
  if (['.sdf', '.mol', '.mol2'].includes(ext)) return 'ligand'
  if (['.cif', '.mmcif', '.ent'].includes(ext)) return 'receptor'
  return 'unknown'
}

/** Ready to dock: prepared, or already a docking input (a PDBQT needs none). */
export function isUsable(mol: MoleculeItem): boolean {
  return (
    mol.status === 'prepared' || (mol.status === 'inspected' && mol.preview?.preparable === false)
  )
}

export interface LoadOutcome {
  added: number
  failed: number
}

export const useMoleculeStore = defineStore('molecules', () => {
  void desktopBridge()

  const molecules = ref<MoleculeItem[]>([])
  const activeId = ref<string | null>(null)
  const filters = ref<FileFilters | null>(null)
  const samples = ref<SampleFile[]>([])
  const query = ref('')
  const filterType = ref<'all' | MoleculeType>('all')
  const filterStatus = ref<'all' | MoleculeStatus>('all')
  const filterCategory = ref<string>('all')
  const inspectingCount = ref(0)

  const activeMolecule = computed(() =>
    molecules.value.find((m) => m.id === activeId.value) ?? null,
  )
  const receptors = computed(() =>
    molecules.value.filter((m) => getEffectiveType(m) === 'receptor'),
  )
  const ligands = computed(() =>
    molecules.value.filter((m) => getEffectiveType(m) === 'ligand'),
  )
  const unknowns = computed(() =>
    molecules.value.filter((m) => getEffectiveType(m) === 'unknown'),
  )
  const isBusy = computed(() => inspectingCount.value > 0)
  const totalBytes = computed(() =>
    molecules.value.reduce((sum, mol) => sum + mol.size, 0),
  )

  /** Distinct categories across all molecules, sorted. */
  const availableCategories = computed(() => {
    const cats = new Set<string>()
    for (const mol of molecules.value) {
      if (mol.category) cats.add(mol.category)
    }
    return [...cats].sort()
  })

  /** Number of active filter conditions. */
  const activeFilterCount = computed(() => {
    let n = 0
    if (filterType.value !== 'all') n++
    if (filterStatus.value !== 'all') n++
    if (filterCategory.value !== 'all') n++
    return n
  })

  /** Whether a molecule passes filters and the search box. */
  function matches(mol: MoleculeItem): boolean {
    // -- type filter --
    if (filterType.value !== 'all' && getEffectiveType(mol) !== filterType.value) {
      return false
    }
    // -- status filter --
    if (filterStatus.value !== 'all' && mol.status !== filterStatus.value) {
      return false
    }
    // -- category filter --
    if (filterCategory.value !== 'all') {
      if (filterCategory.value === '') {
        // "uncategorized" filter
        if (mol.category !== null && mol.category !== '') return false
      } else {
        if (mol.category !== filterCategory.value) return false
      }
    }

    // -- text search (multi-token AND, case-insensitive) --
    const needle = query.value.trim()
    if (!needle) return true

    const tokens = needle
      .toLowerCase()
      .split(/\s+/)
      .filter(Boolean)

    if (tokens.length === 0) return true

    // Build the searchable corpus: name + aliases + category + type + status
    const corpus = [
      mol.name,
      ...mol.aliases,
      mol.category ?? '',
      getEffectiveType(mol),
      mol.status,
    ]
      .join(' ')
      .toLowerCase()

    return tokens.every((token) => corpus.includes(token))
  }

  const visibleReceptors = computed(() => receptors.value.filter(matches))
  const visibleLigands = computed(() => ligands.value.filter(matches))
  const visibleUnknowns = computed(() => unknowns.value.filter(matches))
  const visibleCount = computed(
    () =>
      visibleReceptors.value.length +
      visibleLigands.value.length +
      visibleUnknowns.value.length,
  )

  // -- grouped display (default for library downloads) ----------------------
  const groupedMolecules = computed<MoleculeGroup[]>(() => {
    const groups = new Map<string, MoleculeGroup>()
    const ungrouped: MoleculeItem[] = []

    for (const mol of molecules.value) {
      if (!matches(mol)) continue
      if (mol.groupId) {
        let group = groups.get(mol.groupId)
        if (!group) {
          group = {
            id: mol.groupId,
            name: mol.groupName ?? mol.groupId,
            receptor: null,
            ligands: [],
          }
          groups.set(mol.groupId, group)
        }
        if (getEffectiveType(mol) === 'receptor') {
          group.receptor = mol
        } else {
          group.ligands.push(mol)
        }
      } else {
        ungrouped.push(mol)
      }
    }

    // Sort: groups first (receptor-containing first), then ungrouped molecules
    const result: MoleculeGroup[] = []

    // Groups with receptors first, then groups without
    const withReceptor = [...groups.values()].filter((g) => g.receptor !== null)
    const withoutReceptor = [...groups.values()].filter((g) => g.receptor === null)
    result.push(...withReceptor, ...withoutReceptor)

    // Ungrouped molecules become their own single-item groups
    for (const mol of ungrouped) {
      const key = `single-${mol.id}`
      if (getEffectiveType(mol) === 'receptor') {
        result.unshift({ id: key, name: mol.name, receptor: mol, ligands: [] })
      } else {
        // Find or create a catch-all group for ungrouped ligands
        let catchAll = result.find((g) => g.id === '_ungrouped')
        if (!catchAll) {
          catchAll = { id: '_ungrouped', name: '', receptor: null, ligands: [] }
          result.push(catchAll)
        }
        catchAll.ligands.push(mol)
      }
    }

    return result
  })

  /**
   * Real provenance groups only (a library entry that brought its own receptor
   * and ligands). `groupedMolecules` also synthesises `single-<id>` entries for
   * ungrouped receptors and a `_ungrouped` catch-all for ungrouped ligands —
   * those belong to the "Ungrouped" section, not to the source view's groups.
   */
  const sourceGroups = computed(() =>
    groupedMolecules.value.filter(
      (group) => group.id !== '_ungrouped' && !group.id.startsWith('single-'),
    ),
  )

  // -- pipeline handoff ----------------------------------------------------
  // The docking and box steps act on one chosen molecule of each kind, picked
  // from the usable ones. The choice is explicit — every view offers it — and
  // falls back to the first usable molecule while nothing has been chosen.
  const usableReceptors = computed(() => receptors.value.filter(isUsable))
  const usableLigands = computed(() => ligands.value.filter(isUsable))

  const pipelineReceptorId = ref<string | null>(null)
  const pipelineLigandId = ref<string | null>(null)

  function resolvePick(list: MoleculeItem[], id: string | null): MoleculeItem | null {
    // A chosen molecule that stops being usable steps aside for the fallback;
    // the id is kept, so it resumes its role the moment it is usable again.
    const chosen = id === null ? undefined : list.find((m) => m.id === id)
    return chosen ?? list[0] ?? null
  }

  const pipelineReceptor = computed(() =>
    resolvePick(usableReceptors.value, pipelineReceptorId.value),
  )
  const pipelineLigand = computed(() => resolvePick(usableLigands.value, pipelineLigandId.value))
  const hasReceptor = computed(() => pipelineReceptor.value !== null)
  const hasLigand = computed(() => pipelineLigand.value !== null)

  /** Choose the molecule the downstream steps act on. */
  function setPipelineReceptor(id: string): void {
    if (usableReceptors.value.some((m) => m.id === id)) pipelineReceptorId.value = id
  }

  function setPipelineLigand(id: string): void {
    if (usableLigands.value.some((m) => m.id === id)) pipelineLigandId.value = id
  }

  const receptorReport = computed<ReceptorReport | null>(() => {
    const report = pipelineReceptor.value?.report ?? null
    return report && 'residueList' in report ? report : null
  })
  const ligandReport = computed<LigandReport | null>(() => {
    const report = pipelineLigand.value?.report ?? null
    return report && 'totalCharge' in report ? report : null
  })

  /** The prepared rigid input, or the file itself when it already is one. */
  function rigidPdbqtPath(mol: MoleculeItem | null): string | null {
    if (!mol) return null
    const artifact = mol.artifacts.find((a) => a.kind === 'pdbqt' && !a.name.endsWith('_flex.pdbqt'))
    if (artifact) return artifact.path
    return mol.preview?.preparable === false ? mol.path : null
  }

  const receptorPdbqtPath = computed(() => rigidPdbqtPath(pipelineReceptor.value))
  const ligandPdbqtPath = computed(() => rigidPdbqtPath(pipelineLigand.value))
  const flexReceptorPath = computed(
    () =>
      pipelineReceptor.value?.artifacts.find((a) => a.name.endsWith('_flex.pdbqt'))?.path ?? null,
  )

  /** The drawable copy of the molecule the pipeline uses, for the box viewport. */
  const receptorPdbUrl = computed(() =>
    pipelineReceptor.value ? getPreviewUrl(pipelineReceptor.value) : null,
  )
  const ligandSdfUrl = computed(() =>
    pipelineLigand.value ? getPreviewUrl(pipelineLigand.value) : null,
  )

  async function loadReferenceData(): Promise<void> {
    try {
      const [filterResult, sampleResult] = await Promise.all([api.fileFilters(), api.samples()])
      filters.value = filterResult
      samples.value = sampleResult
    } catch {
      // Non-critical
    }
  }

  function setActive(id: string | null): void {
    activeId.value = id
  }

  function addItem(item: MoleculeItem): void {
    molecules.value.push(item)
    // The molecule just added is the one the user wants to look at.
    activeId.value = item.id
    scheduleSave()
  }

  function removeItem(id: string): void {
    const idx = molecules.value.findIndex((m) => m.id === id)
    if (idx === -1) return
    const removed = molecules.value[idx]
    if (!removed) return
    const previousActive = activeId.value
    const previousReceptor = pipelineReceptorId.value
    const previousLigand = pipelineLigandId.value
    molecules.value.splice(idx, 1)
    if (activeId.value === id) {
      // Prefer the neighbour that takes the removed row's place.
      activeId.value = molecules.value[idx]?.id ?? molecules.value[idx - 1]?.id ?? null
    }
    if (pipelineReceptorId.value === id) pipelineReceptorId.value = null
    if (pipelineLigandId.value === id) pipelineLigandId.value = null
    scheduleSave()
    // Persist removal (fire-and-forget; auto-save will also pick this up).
    void api.deleteMolecule(id).catch(() => {})
    // Only the manifest entry is deleted, never the file, so this is reversible.
    useUndoStore().push(
      i18n.global.t('undo.deleteMolecule', { name: removed.name }),
      () => {
        if (!molecules.value.some((m) => m.id === removed.id)) {
          molecules.value.splice(Math.min(idx, molecules.value.length), 0, removed)
        }
        if (previousActive === removed.id) activeId.value = removed.id
        if (previousReceptor === removed.id) pipelineReceptorId.value = removed.id
        if (previousLigand === removed.id) pipelineLigandId.value = removed.id
        scheduleSave()
      },
    )
  }

  function clearAll(): void {
    if (molecules.value.length === 0) return
    const snapshot = molecules.value.slice()
    const previousActive = activeId.value
    const previousReceptor = pipelineReceptorId.value
    const previousLigand = pipelineLigandId.value
    molecules.value = []
    activeId.value = null
    pipelineReceptorId.value = null
    pipelineLigandId.value = null
    scheduleSave()
    // Persist clear (fire-and-forget; auto-save will also pick this up).
    void api.clearMolecules().catch(() => {})
    useUndoStore().push(
      i18n.global.t('undo.clearMolecules', { count: snapshot.length }),
      () => {
        const existing = new Set(molecules.value.map((m) => m.id))
        molecules.value = [
          ...snapshot.filter((m) => !existing.has(m.id)),
          ...molecules.value,
        ]
        if (previousActive && molecules.value.some((m) => m.id === previousActive)) {
          activeId.value = previousActive
        }
        if (previousReceptor && molecules.value.some((m) => m.id === previousReceptor)) {
          pipelineReceptorId.value = previousReceptor
        }
        if (previousLigand && molecules.value.some((m) => m.id === previousLigand)) {
          pipelineLigandId.value = previousLigand
        }
        scheduleSave()
      },
    )
  }

  function findByPath(path: string): MoleculeItem | undefined {
    return molecules.value.find((m) => m.path === path)
  }

  function findByNameAndSize(name: string, size: number): MoleculeItem | undefined {
    return molecules.value.find((m) => m.name === name && m.size === size)
  }

  function assignType(id: string, type: MoleculeType): void {
    const mol = molecules.value.find((m) => m.id === id)
    if (!mol) return
    // An explicit choice outranks whatever the extension or the file said.
    mol.assignedType = type
    mol.detectionSource = 'user'
    mol.detectionConfidence = 1
    scheduleSave()
  }

  /** Add an alias to a molecule. */
  function addAlias(id: string, alias: string): void {
    const mol = molecules.value.find((m) => m.id === id)
    if (!mol) return
    const trimmed = alias.trim()
    if (!trimmed || mol.aliases.includes(trimmed)) return
    mol.aliases.push(trimmed)
    scheduleSave()
  }

  /** Remove an alias from a molecule. */
  function removeAlias(id: string, alias: string): void {
    const mol = molecules.value.find((m) => m.id === id)
    if (!mol) return
    mol.aliases = mol.aliases.filter((a) => a !== alias)
    scheduleSave()
  }

  /** Set the category of a molecule. Pass null or empty string to clear. */
  function setCategory(id: string, category: string | null): void {
    const mol = molecules.value.find((m) => m.id === id)
    if (!mol) return
    mol.category = category && category.trim() ? category.trim() : null
    scheduleSave()
  }

  /** Reset all filters to defaults. */
  function resetFilters(): void {
    filterType.value = 'all'
    filterStatus.value = 'all'
    filterCategory.value = 'all'
  }

  function addFromPath(
    path: string,
    name?: string,
    size = 0,
    groupId?: string | null,
    groupName?: string | null,
  ): MoleculeItem {
    const derivedName = name ?? path.split('/').pop() ?? path
    const detectedType = detectTypeByExtension(derivedName)

    const item: MoleculeItem = {
      id: generateId(),
      name: derivedName,
      path,
      size,
      detectedType,
      detectionConfidence: detectedType === 'unknown' ? 0.3 : 0.8,
      detectionSource: 'extension',
      detectionReason: 'extension',
      assignedType: null,
      status: 'uploaded',
      preview: null,
      report: null,
      artifacts: [],
      pdbqt: null,
      error: null,
      receptorOptions: { ...DEFAULT_RECEPTOR_OPTIONS },
      ligandOptions: { ...DEFAULT_LIGAND_OPTIONS },
      groupId: groupId ?? null,
      groupName: groupName ?? null,
      aliases: [],
      category: null,
    }
    addItem(item)
    return item
  }

  /**
   * Fetch a copy the 3D viewport can draw.
   *
   * The viewport cannot render PDBQT (no bond orders) or mmCIF, and the loaded
   * file is one of those, so without this the panel stays empty until the user
   * prepares the molecule.
   */
  async function ensureRenderable(mol: MoleculeItem): Promise<void> {
    const kind = getEffectiveType(mol)
    if (kind === 'unknown' || mol.artifacts.length > 0) return
    try {
      mol.artifacts = await api.renderable(mol.path, kind)
    } catch {
      // A missing preview is not a loading failure; the report is still useful.
    }
  }

  function applyResult(
    mol: MoleculeItem,
    kind: 'receptor' | 'ligand',
    preview: unknown,
  ): void {
    mol.preview = preview as MoleculeItem['preview']
    mol.detectedType = kind
    mol.detectionSource = 'content'
    mol.detectionConfidence = 0.95
  }

  /**
   * Describe a molecule and settle what it is.
   *
   * `.pdb` and `.pdbqt` say nothing about the kind, and inspecting such a file as
   * the wrong one used to leave it unclassified with an error nobody could act
   * on, so the other reading is tried before giving up. A reading that succeeds
   * also becomes the molecule's type, so it lands in the right section instead of
   * waiting for the user to file it by hand.
   */
  async function inspectMolecule(id: string): Promise<void> {
    const mol = molecules.value.find((m) => m.id === id)
    if (!mol || mol.status === 'inspecting') return

    mol.status = 'inspecting'
    mol.error = null
    mol.preview = null
    inspectingCount.value += 1

    const known = getEffectiveType(mol)
    let order: Array<'receptor' | 'ligand'> =
      known === 'ligand' ? ['ligand', 'receptor'] : ['receptor', 'ligand']

    if (known === 'unknown') {
      // `.pdb` and `.pdbqt` say nothing about what they hold. The rule that reads
      // the file lives on the server, where it can be tested and shared, so ask
      // it once rather than inspecting one way and trying the other.
      try {
        const detection = await api.detect(mol.path)
        mol.detectionReason = detection.reason
        order = detection.kind === 'ligand' ? ['ligand', 'receptor'] : ['receptor', 'ligand']
      } catch {
        // Detection could not read it either; the inspectors will say why.
      }
    }
    let failure: unknown = null

    try {
      for (const kind of order) {
        try {
          if (kind === 'receptor') {
            applyResult(mol, kind, await api.inspectReceptor(mol.path))
          } else {
            applyResult(mol, kind, await api.inspectLigand(mol.path))
          }
          // Still inspecting until the drawable copy arrives, so the placeholder
          // does not claim the file has no preview while it is on its way.
          await ensureRenderable(mol)
          mol.status = 'inspected'
          scheduleSave()
          return
        } catch (error) {
          failure = failure ?? error
        }
      }

      mol.error = describeFailure(failure)
      mol.status = 'error'
      scheduleSave()
    } finally {
      inspectingCount.value -= 1
    }
  }

  async function prepareMolecule(id: string): Promise<void> {
    const mol = molecules.value.find((m) => m.id === id)
    if (!mol || mol.status === 'preparing') return

    mol.status = 'preparing'
    mol.error = null

    const type = getEffectiveType(mol)
    try {
      if (type === 'receptor') {
        const result = await api.prepareReceptor(mol.path, mol.receptorOptions)
        mol.report = result.report
        mol.artifacts = result.artifacts
      } else {
        const result = await api.prepareLigand(mol.path, mol.ligandOptions)
        mol.report = result.report
        mol.artifacts = result.artifacts
        mol.pdbqt = result.pdbqt
      }
      mol.status = 'prepared'
      scheduleSave()
    } catch (error) {
      mol.error = describeFailure(error)
      mol.status = 'error'
      scheduleSave()
    }
  }

  /**
   * Retry with Meeko's template check relaxed.
   *
   * The structured residue list means the templates could not match those
   * residues; `allow_bad_res` is the option that lets the rest of the structure
   * through. The interface only offers this when residues are actually named,
   * so it never silently weakens a preparation that failed for another reason.
   */
  async function allowRejectedResiduesAndRetry(id: string): Promise<void> {
    const mol = molecules.value.find((m) => m.id === id)
    if (!mol || (mol.error?.residues.length ?? 0) === 0) return
    mol.receptorOptions.allowBadResidues = true
    await prepareMolecule(id)
  }

  /** The residues to treat as flexible side chains on the next preparation. */
  function setFlexibleResidues(id: string, residues: string[]): void {
    const mol = molecules.value.find((m) => m.id === id)
    if (!mol) return
    mol.receptorOptions.flexibleResidues = residues
    scheduleSave()
  }

  /** Water/hetero groups to keep despite the delete switches. */
  function setKeepResidues(id: string, residues: string[]): void {
    const mol = molecules.value.find((m) => m.id === id)
    if (!mol) return
    mol.receptorOptions.keepResidues = residues
    scheduleSave()
  }

  /** Upload browser files, inspecting each one in turn. */
  async function loadFiles(files: File[]): Promise<LoadOutcome> {
    let added = 0
    let failed = 0

    for (const file of files) {
      const existing = findByNameAndSize(file.name, file.size)
      if (existing) {
        setActive(existing.id)
        continue
      }
      try {
        const saved = await api.upload(file)
        const item = addFromPath(saved.path, file.name, file.size)
        added += 1
        await inspectMolecule(item.id)
        if (item.status === 'error') failed += 1
      } catch {
        failed += 1
      }
    }
    return { added, failed }
  }

  /** Register native file paths, inspecting each one in turn. */
  async function loadPaths(paths: string[]): Promise<LoadOutcome> {
    let added = 0
    let failed = 0

    for (const path of paths) {
      if (!path) continue
      const existing = findByPath(path)
      if (existing) {
        setActive(existing.id)
        continue
      }
      const item = addFromPath(path)
      added += 1
      await inspectMolecule(item.id)
      if (item.status === 'error') failed += 1
    }
    return { added, failed }
  }

  /**
   * Build ligands from pasted SMILES (one line = one molecule).
   *
   * The endpoint already inspected and prepared each molecule, so the response
   * carries preview/report/artifacts — applying them skips `inspectMolecule`
   * and leaves the item `prepared`, ready for docking like a file ligand that
   * has been through prepare.
   */
  async function loadFromSmiles(text: string, name?: string): Promise<LoadOutcome> {
    const lines = text
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean)
    if (lines.length === 0) return { added: 0, failed: 0 }

    const body =
      lines.length === 1
        ? { smiles: lines[0], name: name?.trim() || undefined }
        : { smilesList: lines }

    // A domain error (invalid SMILES, empty batch) rejects; the UI surfaces it.
    const items = await api.ligandFromSmiles(body)
    let added = 0
    for (const item of items) {
      const existing = findByPath(item.path)
      if (existing) {
        setActive(existing.id)
        continue
      }
      const mol = addFromPath(item.path, item.name, item.bytes)
      // Backend already ran inspect_ligand + Meeko; do not inspect again.
      mol.assignedType = 'ligand'
      mol.detectedType = 'ligand'
      mol.detectionSource = 'content'
      mol.detectionConfidence = 0.95
      mol.detectionReason = 'small molecule'
      mol.preview = item.preview
      mol.report = item.preparation.report
      mol.artifacts = item.preparation.artifacts
      mol.pdbqt = item.preparation.pdbqt
      mol.status = 'prepared'
      scheduleSave()
      added += 1
    }
    return { added, failed: 0 }
  }

  /** Add one of the reference structures the application ships with. */
  async function loadSample(sample: SampleFile): Promise<void> {
    const existing = findByPath(sample.path)
    if (existing) {
      setActive(existing.id)
      return
    }
    const item = addFromPath(sample.path, sample.name, sample.bytes)
    await inspectMolecule(item.id)
  }

  /** Add a molecule downloaded from the RCSB library. */
  async function loadFromLibrary(
    path: string,
    name: string,
    size: number,
    kind: 'receptor' | 'ligand',
    groupId?: string,
    groupName?: string,
  ): Promise<void> {
    const existing = findByPath(path)
    if (existing) {
      setActive(existing.id)
      return
    }
    const item = addFromPath(path, name, size, groupId, groupName)
    item.assignedType = kind
    item.detectionSource = 'user'
    item.detectionConfidence = 1
    await inspectMolecule(item.id)
  }

  /**
   * Download receptor + all ligands from a library entry and group them.
   *
   * `fetchReceptor` and `fetchLigands` are the pre-fetched results from the
   * backend.  Each entry in `fetchLigands` is a `{ pdbId, name, path, bytes }`.
   */
  async function loadFromLibraryGroup(
    receptor: LibraryFetchResponse,
    ligands: Array<{ path: string; name: string; bytes: number }>,
    groupName: string,
  ): Promise<void> {
    const groupId = `lib-${receptor.pdbId.toLowerCase()}`

    // Add receptor first
    await loadFromLibrary(receptor.path, receptor.name, receptor.bytes, 'receptor', groupId, groupName)

    // Add ligands in parallel (non-blocking)
    const tasks = ligands.map((lig) =>
      loadFromLibrary(lig.path, lig.name, lig.bytes, 'ligand', groupId, groupName),
    )
    await Promise.allSettled(tasks)
  }

  function getPreviewUrl(mol: MoleculeItem): string | null {
    const type = getEffectiveType(mol)
    if (type === 'receptor') {
      return mol.artifacts.find((a) => a.kind === 'pdb')?.url ?? null
    }
    return mol.artifacts.find((a) => a.kind === 'sdf')?.url ?? null
  }

  // ── manifest persistence ────────────────────────────────────────────────

  const isDirty = ref(false)

  /** Convert an in-memory MoleculeItem to the wire format for the manifest. */
  function toManifestEntry(mol: MoleculeItem): MoleculeManifestEntry {
    return {
      id: mol.id,
      name: mol.name,
      path: mol.path,
      size: mol.size,
      detectedType: mol.detectedType,
      detectionConfidence: mol.detectionConfidence,
      detectionSource: mol.detectionSource,
      detectionReason: mol.detectionReason,
      assignedType: mol.assignedType,
      status: mol.status,
      preview: mol.preview,
      report: mol.report,
      artifacts: mol.artifacts,
      pdbqt: mol.pdbqt,
      error: mol.error,
      receptorOptions: { ...mol.receptorOptions },
      ligandOptions: { ...mol.ligandOptions },
      groupId: mol.groupId,
      groupName: mol.groupName,
      aliases: [...mol.aliases],
      category: mol.category,
      mtime: null,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    }
  }

  /** Convert a manifest entry back to an in-memory MoleculeItem. */
  function fromManifestEntry(entry: MoleculeManifestEntry): MoleculeItem {
    return {
      id: entry.id,
      name: entry.name,
      path: entry.path,
      size: entry.size,
      detectedType: entry.detectedType,
      detectionConfidence: entry.detectionConfidence,
      detectionSource: entry.detectionSource,
      detectionReason: entry.detectionReason as MoleculeItem['detectionReason'],
      assignedType: entry.assignedType,
      status: entry.status,
      preview: entry.preview as MoleculeItem['preview'],
      report: entry.report as MoleculeItem['report'],
      artifacts: entry.artifacts ?? [],
      pdbqt: entry.pdbqt,
      error: entry.error as MoleculeItem['error'],
      receptorOptions: { ...DEFAULT_RECEPTOR_OPTIONS, ...entry.receptorOptions },
      ligandOptions: { ...DEFAULT_LIGAND_OPTIONS, ...entry.ligandOptions },
      groupId: entry.groupId,
      groupName: entry.groupName,
      aliases: entry.aliases ?? [],
      category: entry.category ?? null,
    }
  }

  /** Save the current molecule list to the backend manifest. */
  async function saveToManifest(): Promise<void> {
    try {
      const manifest: MoleculeManifest = {
        formatVersion: '1.0',
        updatedAt: new Date().toISOString(),
        molecules: molecules.value.map(toManifestEntry),
      }
      await api.saveMolecules(manifest)
      isDirty.value = false
    } catch (err) {
      console.error('[molecules] saveToManifest failed:', err)
    }
  }

  // Debounced auto-save: coalesces rapid mutations into a single save.
  let saveTimer: ReturnType<typeof setTimeout> | null = null
  let isSaving = false

  function scheduleSave(): void {
    isDirty.value = true
    if (saveTimer !== null) clearTimeout(saveTimer)
    saveTimer = setTimeout(async () => {
      if (isSaving) return
      isSaving = true
      try {
        await saveToManifest()
      } finally {
        isSaving = false
      }
    }, 2000)
  }

  /** Load the molecule list from the backend manifest. */
  async function loadFromManifest(): Promise<void> {
    try {
      const manifest = await api.listMolecules()
      if (!manifest?.molecules?.length) return

      // Deduplicate by path — keep the first occurrence.
      const seen = new Set<string>()
      for (const entry of manifest.molecules) {
        if (seen.has(entry.path)) continue
        seen.add(entry.path)
        const item = fromManifestEntry(entry)
        molecules.value.push(item)
      }
      isDirty.value = false

      // Verify file existence and staleness in the background.
      const ids = molecules.value.map((m) => m.id)
      if (ids.length === 0) return

      api.verifyMolecules(ids).then(({ existing, missing, mtimes }) => {
        // Mark missing files as errors.
        for (const id of missing) {
          const mol = molecules.value.find((m) => m.id === id)
          if (mol && mol.status !== 'error') {
            mol.status = 'error'
            mol.error = { kind: 'FileNotFound', detail: 'File not found on disk' } as never
          }
        }

        // Queue re-inspection for molecules that need it:
        // - Never inspected (status === 'uploaded')
        // - File changed since last inspection (mtime mismatch)
        const needsInspect: string[] = []
        for (const id of existing) {
          const mol = molecules.value.find((m) => m.id === id)
          if (!mol) continue
          if (mol.status === 'uploaded') {
            needsInspect.push(id)
          } else if (mtimes[id] && mol.status === 'inspected' || mol.status === 'prepared') {
            // File changed — re-inspect to refresh preview/artifacts.
            // Only if the file actually changed (mtime differs from stored).
            // For now, skip re-inspection of prepared molecules to avoid
            // losing preparation work; the user can manually re-prepare.
          }
        }

        // Background re-inspection: process one at a time, non-blocking.
        if (needsInspect.length > 0) {
          void inspectQueued(needsInspect)
        }
      }).catch(() => {
        // Verification is best-effort; don't break the load.
      })
    } catch (err) {
      console.error('[molecules] loadFromManifest failed:', err)
    }
  }

  /** Sequentially inspect a list of molecule IDs in the background. */
  async function inspectQueued(ids: string[]): Promise<void> {
    for (const id of ids) {
      // Stop if the molecule was removed while we were inspecting.
      if (!molecules.value.find((m) => m.id === id)) continue
      await inspectMolecule(id)
      // Yield to the event loop between inspections.
      await new Promise((r) => setTimeout(r, 50))
    }
  }

  return {
    molecules,
    activeId,
    activeMolecule,
    receptors,
    ligands,
    unknowns,
    query,
    visibleReceptors,
    visibleLigands,
    visibleUnknowns,
    visibleCount,
    isBusy,
    totalBytes,
    usableReceptors,
    usableLigands,
    pipelineReceptor,
    pipelineLigand,
    setPipelineReceptor,
    setPipelineLigand,
    rigidPdbqtPath,
    hasReceptor,
    hasLigand,
    receptorReport,
    ligandReport,
    receptorPdbqtPath,
    ligandPdbqtPath,
    flexReceptorPath,
    receptorPdbUrl,
    ligandSdfUrl,
    filters,
    samples,
    loadReferenceData,
    setActive,
    addItem,
    removeItem,
    clearAll,
    findByPath,
    assignType,
    addAlias,
    removeAlias,
    setCategory,
    resetFilters,
    filterType,
    filterStatus,
    filterCategory,
    availableCategories,
    activeFilterCount,
    addFromPath,
    loadFromLibrary,
    loadFromLibraryGroup,
    groupedMolecules,
    sourceGroups,
    inspectMolecule,
    prepareMolecule,
    allowRejectedResiduesAndRetry,
    setFlexibleResidues,
    setKeepResidues,
    loadFiles,
    loadPaths,
    loadFromSmiles,
    loadSample,
    getPreviewUrl,
    isDirty,
    saveToManifest,
    loadFromManifest,
  }
})
