/** Reactive state for the sketcher: tools, history, selection, analysis.

    One instance is created by `SketcherDialog` and provided to the toolbar
    and canvas via `sketcherKey`.  Mutations only ever land through `commit`,
    which snapshots first (undo ≤100 entries, deduped before push).
*/

import {
  computed,
  inject,
  provide,
  ref,
  watch,
  type ComputedRef,
  type InjectionKey,
  type Ref,
} from 'vue'

import { api } from '@/api/http'
import type { SketchAnalyzeResponse, SketchAtomInput, SketchBondInput } from '@/types/api'

import {
  ANGSTROM_PER_PX,
  planRingFusion,
  type Point,
  type RingTarget,
  type RingTemplateSpec,
  type View,
} from './geometry'
import {
  addAtom,
  addBond,
  atomById,
  cloneSnapshot,
  connectedComponent,
  emptySnapshot,
  findBond,
  removeAtom,
  removeBond,
  snapshotsEqual,
  type SketchSnapshot,
} from './model'

export type SketchTool =
  | 'select'
  | 'atom'
  | 'bond'
  | 'erase'
  | 'charge+'
  | 'charge-'
  | 'template'
  | 'chain'
  | 'radical'

/** Panel elements; the letter shortcuts cover the same set (task book §4.3). */
export const ELEMENT_PANEL = ['C', 'N', 'O', 'S', 'P', 'F', 'Cl', 'Br', 'I', 'B', 'Si'] as const

const HISTORY_LIMIT = 100
const ANALYZE_DEBOUNCE_MS = 300

/** Live pointer target: written by SketcherCanvas, read by the template ghost
    and the dialog keyboard (MoleditPy routes both from itemAtCursorPosition). */
export interface SketchPointer {
  atomId: number | null
  bond: readonly [number, number] | null
  /** Scene point under the pointer; null while the cursor is off-canvas. */
  scene: Point | null
}

export interface SketcherState {
  snapshot: Ref<SketchSnapshot>
  tool: Ref<SketchTool>
  symbol: Ref<string>
  bondOrder: Ref<1 | 2 | 3>
  bondStereo: Ref<0 | 1 | 2>
  /** Ring template picked in the toolbar palette (task book 4.4). */
  templateSize: Ref<number>
  templateBenzene: Ref<boolean>
  /** Hetero template id; null = a carbocycle button (numeric/Bz) is picked. */
  templateId: Ref<string | null>
  /** Vertex symbols for the picked hetero ring; null = all-carbon. */
  templateSymbols: Ref<string[] | null>
  selection: Ref<number[]>
  selectedBond: Ref<readonly [number, number] | null>
  /** Pointer hit + scene position (canvas writes; keyboard/ghost read). */
  pointer: Ref<SketchPointer>
  view: Ref<View>
  /** Canvas pixel box, written by SketcherCanvas — cleanup centres on it. */
  canvasSize: Ref<{ w: number; h: number }>
  analysis: Ref<SketchAnalyzeResponse | null>
  analyzeState: Ref<'idle' | 'pending' | 'ok' | 'error'>
  hasStructure: ComputedRef<boolean>
  /** True only while `analysis` describes the graph exactly on screen. */
  exportable: ComputedRef<boolean>
  canUndo: ComputedRef<boolean>
  canRedo: ComputedRef<boolean>
  commit(mutator: (snapshot: SketchSnapshot) => void): boolean
  /** Place a template ring as one commit; false when the plan was empty. */
  placeRing(target: RingTarget, spec?: RingTemplateSpec): boolean
  /** rdDepictor tidy-up + centre; false when the request failed. */
  cleanup(): Promise<boolean>
  /** Replace the whole drawing from a layout (one commit → one undo). */
  importLayout(atoms: SketchAtomInput[], bonds: SketchBondInput[]): boolean
  undo(): void
  redo(): void
  clearSelection(): void
  selectComponent(startId: number): void
  deleteSelection(): boolean
  reset(): void
}

export const sketcherKey: InjectionKey<SketcherState> = Symbol('sketcher-state')

export function useSketcher(): SketcherState {
  const snapshot = ref<SketchSnapshot>(emptySnapshot())
  const past = ref<SketchSnapshot[]>([])
  const future = ref<SketchSnapshot[]>([])
  const tool = ref<SketchTool>('atom')
  const symbol = ref('C')
  const bondOrder = ref<1 | 2 | 3>(1)
  const bondStereo = ref<0 | 1 | 2>(0)
  const templateSize = ref(6)
  const templateBenzene = ref(false)
  const templateId = ref<string | null>(null)
  const templateSymbols = ref<string[] | null>(null)
  const selection = ref<number[]>([])
  const selectedBond = ref<readonly [number, number] | null>(null)
  const pointer = ref<SketchPointer>({ atomId: null, bond: null, scene: null })
  const view = ref<View>({ zoom: 1, panX: 0, panY: 0 })
  const canvasSize = ref({ w: 0, h: 0 })
  const analysis = ref<SketchAnalyzeResponse | null>(null)
  const analyzeState = ref<'idle' | 'pending' | 'ok' | 'error'>('idle')
  const analyzedSignature = ref('')

  let analyzeTimer: ReturnType<typeof setTimeout> | undefined
  let analyzeSeq = 0

  const currentSignature = computed(() =>
    JSON.stringify([snapshot.value.atoms, snapshot.value.bonds]),
  )
  const hasStructure = computed(() => snapshot.value.atoms.length > 0)
  // Export must never ship a stale verdict: the signature pins the analysis
  // to the exact graph on screen, so any in-between edit disables the button
  // until the debounced round-trip lands.
  const exportable = computed(
    () => !!analysis.value?.smiles && analyzedSignature.value === currentSignature.value,
  )
  const canUndo = computed(() => past.value.length > 0)
  const canRedo = computed(() => future.value.length > 0)

  function clearSelection(): void {
    selection.value = []
    selectedBond.value = null
  }

  /** Angstrom chemical frame → scene px: scale up and flip y — the exact
      mirror of build_mol's px → Angstrom conversion.  Shared by cleanup and
      the SMILES importer so both land the same orientation. */
  function toScene(x: number, y: number): { x: number; y: number } {
    return { x: x / ANGSTROM_PER_PX, y: -y / ANGSTROM_PER_PX }
  }

  function centreViewOn(centre: { x: number; y: number }): void {
    const size = canvasSize.value
    if (size.w <= 0 || size.h <= 0) return
    const { zoom } = view.value
    view.value = { zoom, panX: size.w / 2 - centre.x * zoom, panY: size.h / 2 - centre.y * zoom }
  }

  function commit(mutator: (snapshot: SketchSnapshot) => void): boolean {
    const before = cloneSnapshot(snapshot.value)
    mutator(snapshot.value)
    if (snapshotsEqual(before, snapshot.value)) return false
    const top = past.value[past.value.length - 1]
    // Dedup before push: pointer handlers commit on every release, and a
    // release that changed nothing must not bury the real undo steps.
    if (!top || !snapshotsEqual(top, before)) {
      past.value.push(before)
      if (past.value.length > HISTORY_LIMIT) past.value.shift()
    }
    future.value = []
    selection.value = selection.value.filter((id) => atomById(snapshot.value, id))
    if (selectedBond.value) {
      const [a1, a2] = selectedBond.value
      if (!findBond(snapshot.value, a1, a2)) selectedBond.value = null
    }
    return true
  }

  /** One commit for a whole ring placement — canvas click, template ghost
      accept and the `4` shortcut all land through here so a single undo
      removes the entire ring (MoleditPy's one-shot template insertion). */
  function placeRing(target: RingTarget, spec?: RingTemplateSpec): boolean {
    const plan = planRingFusion(
      snapshot.value,
      target,
      spec ?? {
        size: templateSize.value,
        benzene: templateBenzene.value,
        symbols: templateSymbols.value ?? undefined,
      },
    )
    if (!plan) return false
    return commit((s) => {
      const created = plan.newAtoms.map((atom) => addAtom(s, atom.symbol, atom.x, atom.y).id)
      const resolve = (ref: number) => (ref > 0 ? ref : created[-ref - 1])
      for (const bond of plan.newBonds) {
        const a1 = resolve(bond.a1)
        const a2 = resolve(bond.a2)
        if (a1 !== undefined && a2 !== undefined) addBond(s, a1, a2, bond.order, 0)
      }
    })
  }

  async function cleanup(): Promise<boolean> {
    if (!hasStructure.value) return false
    try {
      const result = await api.cleanupSketch({
        atoms: snapshot.value.atoms,
        bonds: snapshot.value.bonds,
      })
      let centre = { x: 0, y: 0 }
      // The mutator runs even when nothing changes (commit then skips the
      // history entry), so the centre is known either way and the view can
      // re-centre on an already-tidy drawing too.
      commit((current) => {
        let sumX = 0
        let sumY = 0
        for (const atom of current.atoms) {
          const position = result.positions[atom.id]
          if (position) {
            const point = toScene(position[0], position[1])
            atom.x = point.x
            atom.y = point.y
          }
          sumX += atom.x
          sumY += atom.y
        }
        if (current.atoms.length) {
          centre = { x: sumX / current.atoms.length, y: sumY / current.atoms.length }
        }
      })
      // The mutator ran even when nothing changed, so the centre is known
      // either way and an already-tidy drawing re-centres too.
      centreViewOn(centre)
      return true
    } catch {
      // Transport/422: the toolbar turns false into a toast; the drawing
      // stays exactly as it was.
      return false
    }
  }

  /** Whole-canvas replacement from a SMILES layout: exactly one commit, so a
      single undo restores whatever the user had drawn (task book C5). */
  function importLayout(atoms: SketchAtomInput[], bonds: SketchBondInput[]): boolean {
    if (atoms.length === 0) return false
    let centre = { x: 0, y: 0 }
    const replaced = commit((current) => {
      current.atoms = []
      current.bonds = []
      let sumX = 0
      let sumY = 0
      for (const source of atoms) {
        const point = toScene(source.x, source.y)
        current.atoms.push({
          id: source.id,
          symbol: source.symbol,
          x: point.x,
          y: point.y,
          charge: source.charge,
          radical: source.radical,
        })
        sumX += point.x
        sumY += point.y
      }
      for (const source of bonds) {
        // Layout orders arrive as numbers; the model pins the union 1|2|3.
        const order = source.order >= 3 ? 3 : source.order >= 2 ? 2 : 1
        const stereo = source.stereo >= 2 ? 2 : source.stereo >= 1 ? 1 : 0
        current.bonds.push({
          a1: source.a1,
          a2: source.a2,
          order: order as 1 | 2 | 3,
          stereo: stereo as 0 | 1 | 2,
        })
      }
      // Ids restart at the layout's own numbering; nextId must clear them all.
      current.nextId = Math.max(...atoms.map((atom) => atom.id)) + 1
      centre = { x: sumX / atoms.length, y: sumY / atoms.length }
    })
    centreViewOn(centre)
    return replaced
  }

  function undo(): void {
    const previous = past.value.pop()
    if (!previous) return
    future.value.push(cloneSnapshot(snapshot.value))
    snapshot.value = previous
    clearSelection()
  }

  function redo(): void {
    const next = future.value.pop()
    if (!next) return
    past.value.push(cloneSnapshot(snapshot.value))
    snapshot.value = next
    clearSelection()
  }

  function selectComponent(startId: number): void {
    selection.value = connectedComponent(snapshot.value, startId)
    selectedBond.value = null
  }

  function deleteSelection(): boolean {
    const ids = [...selection.value]
    const bond = selectedBond.value
    if (ids.length === 0 && !bond) return false
    return commit((current) => {
      // Removing an atom takes its bonds with it; the explicit bond removal
      // only matters when the selection is a bond between surviving atoms.
      for (const id of ids) removeAtom(current, id)
      if (bond) removeBond(current, bond[0], bond[1])
    })
  }

  function scheduleAnalyze(): void {
    window.clearTimeout(analyzeTimer)
    if (snapshot.value.atoms.length === 0) {
      // Invalidate anything in flight: an empty canvas is its own verdict.
      analyzeSeq += 1
      analysis.value = null
      analyzedSignature.value = ''
      analyzeState.value = 'idle'
      return
    }
    analyzeState.value = 'pending'
    analyzeTimer = setTimeout(() => void runAnalyze(), ANALYZE_DEBOUNCE_MS)
  }

  async function runAnalyze(): Promise<void> {
    const seq = ++analyzeSeq
    const signature = currentSignature.value
    try {
      const result = await api.analyzeSketch({
        atoms: snapshot.value.atoms,
        bonds: snapshot.value.bonds,
      })
      if (seq !== analyzeSeq) return // a newer request already answered
      analysis.value = result
      analyzedSignature.value = signature
      analyzeState.value = 'ok'
    } catch {
      if (seq !== analyzeSeq) return
      // Keep the last verdict on screen; the signature mismatch keeps export
      // disabled, so a transport failure can never ship stale SMILES.
      analyzeState.value = 'error'
    }
  }

  function reset(): void {
    window.clearTimeout(analyzeTimer)
    analyzeSeq += 1
    snapshot.value = emptySnapshot()
    past.value = []
    future.value = []
    clearSelection()
    pointer.value = { atomId: null, bond: null, scene: null }
    analysis.value = null
    analyzedSignature.value = ''
    analyzeState.value = 'idle'
    view.value = { zoom: 1, panX: 0, panY: 0 }
  }

  watch(snapshot, scheduleAnalyze, { deep: true })

  return {
    snapshot,
    tool,
    symbol,
    bondOrder,
    bondStereo,
    templateSize,
    templateBenzene,
    templateId,
    templateSymbols,
    selection,
    selectedBond,
    pointer,
    view,
    canvasSize,
    analysis,
    analyzeState,
    hasStructure,
    exportable,
    canUndo,
    canRedo,
    commit,
    placeRing,
    cleanup,
    importLayout,
    undo,
    redo,
    clearSelection,
    selectComponent,
    deleteSelection,
    reset,
  }
}

export function provideSketcher(state: SketcherState): void {
  provide(sketcherKey, state)
}

export function injectSketcher(): SketcherState {
  const state = inject(sketcherKey)
  if (!state) throw new Error('sketcher state missing: SketcherDialog must provide it')
  return state
}
