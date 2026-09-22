import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { desktopBridge } from '@/api/bridge'
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
import type { MoleculeGroup, MoleculeItem, MoleculeType } from '@/types/molecule'
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

  /** Whether a molecule passes the search box. Every section filters the same way. */
  function matches(mol: MoleculeItem): boolean {
    const needle = query.value.trim().toLowerCase()
    return !needle || mol.name.toLowerCase().includes(needle)
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
  }

  function removeItem(id: string): void {
    const idx = molecules.value.findIndex((m) => m.id === id)
    if (idx === -1) return
    molecules.value.splice(idx, 1)
    if (activeId.value === id) {
      // Prefer the neighbour that takes the removed row's place.
      activeId.value = molecules.value[idx]?.id ?? molecules.value[idx - 1]?.id ?? null
    }
    if (pipelineReceptorId.value === id) pipelineReceptorId.value = null
    if (pipelineLigandId.value === id) pipelineLigandId.value = null
  }

  function clearAll(): void {
    molecules.value = []
    activeId.value = null
    pipelineReceptorId.value = null
    pipelineLigandId.value = null
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
          return
        } catch (error) {
          failure = failure ?? error
        }
      }

      mol.error = describeFailure(failure)
      mol.status = 'error'
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
    } catch (error) {
      mol.error = describeFailure(error)
      mol.status = 'error'
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
    addFromPath,
    loadFromLibrary,
    loadFromLibraryGroup,
    groupedMolecules,
    inspectMolecule,
    prepareMolecule,
    allowRejectedResiduesAndRetry,
    setFlexibleResidues,
    loadFiles,
    loadPaths,
    loadSample,
    getPreviewUrl,
  }
})
