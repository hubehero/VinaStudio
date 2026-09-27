<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import {
  DRAG_THRESHOLD_PX,
  SNAP_PX,
  WEDGE_HALF,
  atomNear,
  bondNear,
  chainAxes,
  chainPoints,
  clampZoom,
  dashTicks,
  distance,
  ellipseExitT,
  labelBox,
  planRingFusion,
  ringDoubleShortenFactor,
  screenToScene,
  zoomAt,
  type Point,
  type RingTarget,
  type View,
} from './geometry'
import {
  addAtom,
  addBond,
  atomById,
  bondKey,
  bondsOf,
  findBond,
  isSkeletonCarbon,
  removeAtom,
  removeBond,
  type SketchSnapshot,
} from './model'
import { injectSketcher, type SketchPointer } from './state'

const state = injectSketcher()
const { t } = useI18n()

const hostEl = ref<HTMLDivElement | null>(null)
const svgEl = ref<SVGSVGElement | null>(null)
const size = ref({ w: 960, h: 640 })

let observer: ResizeObserver | null = null
let centered = false

onMounted(() => {
  const host = hostEl.value
  if (!host) return
  const sync = () => {
    size.value = { w: host.clientWidth || 960, h: host.clientHeight || 640 }
    state.canvasSize.value = size.value
    // Scene origin sits at the container centre so the first atom lands in
    // view instead of in the top-left corner.
    if (!centered) {
      centered = true
      state.view.value = { zoom: 1, panX: size.value.w / 2, panY: size.value.h / 2 }
    }
  }
  sync()
  observer = new ResizeObserver(sync)
  observer.observe(host)
  window.addEventListener('keydown', onAltDown)
  window.addEventListener('keyup', onAltUp)
  window.addEventListener('blur', onAltBlur)
})

onBeforeUnmount(() => {
  observer?.disconnect()
  window.removeEventListener('keydown', onAltDown)
  window.removeEventListener('keyup', onAltUp)
  window.removeEventListener('blur', onAltBlur)
})

const viewBox = computed(() => {
  const { zoom, panX, panY } = state.view.value
  return `${-panX / zoom} ${-panY / zoom} ${size.value.w / zoom} ${size.value.h / zoom}`
})

// ---------------------------------------------------------------------------
// Pointer state machine (MoleditPy mouse matrix: press → drag kind → release)
// ---------------------------------------------------------------------------

interface Press {
  screen: Point
  scene: Point
  atomId: number | null
  bond: { a1: number; a2: number } | null
  /** Shift held at press time; selection semantics read it on release. */
  shift: boolean
  /** Select-mode: the pressed atom was already selected — a click releases
      it (MoleditPy's was_selected_on_press). */
  wasSelected: boolean
  /** View at press so a shift-drag can pan from the original frame. */
  view: View
}

const press = ref<Press | null>(null)
const dragKind = ref<'none' | 'pan' | 'band' | 'move' | 'rubber'>('none')
const moveDelta = ref<Point | null>(null)
const panOrigin = ref<{ screen: Point; view: View } | null>(null)
// Alt suppresses ghost fusion (MoleditPy: free placement while held).
const altHeld = ref(false)

function onAltDown(e: KeyboardEvent): void {
  if (e.key === 'Alt') altHeld.value = true
}

function onAltUp(e: KeyboardEvent): void {
  if (e.key === 'Alt') altHeld.value = false
}

function onAltBlur(): void {
  altHeld.value = false
}

function svgPoint(e: { clientX: number; clientY: number }): Point {
  const rect = svgEl.value?.getBoundingClientRect()
  if (!rect) return { x: 0, y: 0 }
  return { x: e.clientX - rect.left, y: e.clientY - rect.top }
}

function sceneAt(e: { clientX: number; clientY: number }): Point {
  const p = svgPoint(e)
  return screenToScene(p.x, p.y, state.view.value)
}

/** Hit test + scene point: the single source for hover, press and context menu. */
function pointerTarget(scene: Point): SketchPointer {
  const radius = SNAP_PX / state.view.value.zoom
  const atomId = atomNear(state.snapshot.value, scene, radius)
  const bond = atomId === null ? bondNear(state.snapshot.value, scene, radius) : null
  return { atomId, bond: bond ? [bond.a1, bond.a2] : null, scene }
}

function clearPointer(): void {
  state.pointer.value = { atomId: null, bond: null, scene: null }
}

function onPointerDown(e: PointerEvent): void {
  if (e.button === 1) {
    dragKind.value = 'pan'
    panOrigin.value = { screen: svgPoint(e), view: { ...state.view.value } }
    svgEl.value?.setPointerCapture(e.pointerId)
    return
  }
  if (e.button !== 0) return
  const screen = svgPoint(e)
  const scene = screenToScene(screen.x, screen.y, state.view.value)
  const target = pointerTarget(scene)
  const tool = state.tool.value
  press.value = {
    screen,
    scene,
    atomId: target.atomId,
    bond: target.bond ? { a1: target.bond[0], a2: target.bond[1] } : null,
    shift: e.shiftKey,
    wasSelected:
      tool === 'select' && target.atomId !== null && state.selection.value.includes(target.atomId),
    view: { ...state.view.value },
  }
  state.pointer.value = target
  moveDelta.value = null
  // The temp line is armed AT PRESS (MoleditPy): bond/atom/chain show their
  // rubber immediately — not after the drag threshold.  Shift+click skips it
  // so the modifier keeps its selection/pan meaning.
  dragKind.value =
    !e.shiftKey && (tool === 'bond' || tool === 'atom' || tool === 'chain') ? 'rubber' : 'none'
  svgEl.value?.setPointerCapture(e.pointerId)
}

function onPointerMove(e: PointerEvent): void {
  const screen = svgPoint(e)
  const scene = screenToScene(screen.x, screen.y, state.view.value)

  if (dragKind.value === 'pan' && panOrigin.value) {
    const origin = panOrigin.value
    state.view.value = {
      zoom: origin.view.zoom,
      panX: origin.view.panX + (screen.x - origin.screen.x),
      panY: origin.view.panY + (screen.y - origin.screen.y),
    }
    return
  }

  const current = press.value
  if (state.tool.value === 'template' && !current) {
    // The ghost tracks the pointer even without a press (MoleditPy move
    // handler updates the preview on every motion).
    state.pointer.value = pointerTarget(scene)
    return
  }
  if (!current) {
    state.pointer.value = pointerTarget(scene)
    return
  }
  // Pressed: the hit target stays frozen (no fighting the drag) but the
  // scene point stays live; the template ghost keeps full tracking.
  state.pointer.value =
    state.tool.value === 'template' ? pointerTarget(scene) : { ...state.pointer.value, scene }

  if (dragKind.value === 'none') {
    if (distance(screen, current.screen) <= DRAG_THRESHOLD_PX) return
    // Shift+left-drag pans (MoleditPy view); shift+click keeps its meaning.
    if (current.shift) {
      dragKind.value = 'pan'
      panOrigin.value = { screen: current.screen, view: current.view }
      return
    }
    const tool = state.tool.value
    if (tool === 'select') dragKind.value = current.atomId !== null ? 'move' : 'band'
    else if (tool === 'bond' || tool === 'atom' || tool === 'chain') dragKind.value = 'rubber'
    if (dragKind.value === 'none') return
  }

  if (dragKind.value === 'move') {
    moveDelta.value = { x: scene.x - current.scene.x, y: scene.y - current.scene.y }
  }
}

function onPointerUp(e: PointerEvent): void {
  const current = press.value
  const kind = dragKind.value
  const delta = moveDelta.value
  if (svgEl.value?.hasPointerCapture(e.pointerId)) svgEl.value.releasePointerCapture(e.pointerId)
  press.value = null
  dragKind.value = 'none'
  moveDelta.value = null
  panOrigin.value = null
  if (!current) return
  if (kind === 'pan') return
  const screen = svgPoint(e)
  const scene = screenToScene(screen.x, screen.y, state.view.value)
  // Qt's is_click: manhattan travel below startDragDistance decides the
  // click-vs-drag semantics of the release.
  const isClick = Math.abs(screen.x - current.screen.x) + Math.abs(screen.y - current.screen.y) <= DRAG_THRESHOLD_PX

  if (kind === 'band') {
    selectBox(current.scene, scene)
    state.pointer.value = pointerTarget(scene)
    return
  }
  if (kind === 'move' && current.atomId !== null && delta && Math.hypot(delta.x, delta.y) >= 1) {
    commitMove(current.atomId, delta)
    state.pointer.value = pointerTarget(scene)
    return
  }
  if (kind === 'rubber') {
    if (isClick) handleClick(current, scene)
    else dragCreate(current, scene)
    state.pointer.value = pointerTarget(scene)
    return
  }
  // kind 'none': a plain click (or a shift-click that never travelled).
  handleClick(current, scene)
  state.pointer.value = pointerTarget(scene)
}

/** Tools where right-click zeroes/does nothing instead of deleting. */
const NO_DELETE_TOOLS = new Set(['template', 'charge+', 'charge-', 'radical'])

function onContextMenu(e: MouseEvent): void {
  const hit = pointerTarget(sceneAt(e))
  const tool = state.tool.value
  if (hit.atomId !== null) {
    const id = hit.atomId
    if (NO_DELETE_TOOLS.has(tool)) {
      // Radical/charge modes reset their attribute; template never deletes.
      if (tool === 'radical') {
        state.commit((s) => {
          const atom = atomById(s, id)
          if (atom) atom.radical = 0
        })
      } else if (tool === 'charge+' || tool === 'charge-') {
        state.commit((s) => {
          const atom = atomById(s, id)
          if (atom) atom.charge = 0
        })
      }
      return
    }
    const selection = state.selection.value
    if (selection.length > 1 && selection.includes(id)) {
      // Right-click inside a multi-selection clears the whole selection
      // (MoleditPy deletes the entire selectedItems set).
      state.deleteSelection()
      return
    }
    state.commit((s) => removeAtom(s, id))
    return
  }
  if (hit.bond) {
    const [a1, a2] = hit.bond
    if (NO_DELETE_TOOLS.has(tool)) return
    const selected = state.selectedBond.value
    const inSelection =
      !!selected && bondKey(selected[0], selected[1]) === bondKey(a1, a2) && state.selection.value.length > 0
    if (inSelection) {
      state.deleteSelection()
      return
    }
    state.commit((s) => removeBond(s, a1, a2))
  }
}

function onDoubleClick(e: MouseEvent): void {
  if (state.tool.value !== 'select') return
  const hit = pointerTarget(sceneAt(e))
  if (hit.atomId !== null) state.selectComponent(hit.atomId)
  else if (hit.bond) state.selectComponent(hit.bond[0])
}

function onWheel(e: WheelEvent): void {
  const p = svgPoint(e)
  const factor = Math.exp(-e.deltaY * 0.0015)
  state.view.value = zoomAt(state.view.value, factor, p.x, p.y)
}

// ---------------------------------------------------------------------------
// View controls (task book C7): fit / 100% / step zoom, clamp 0.25–6
// ---------------------------------------------------------------------------

/** Frame every atom with a margin; falls back to 100% on an empty canvas. */
function fitView(): void {
  const atoms = state.snapshot.value.atoms
  if (atoms.length === 0) {
    resetView()
    return
  }
  let minX = Infinity
  let minY = Infinity
  let maxX = -Infinity
  let maxY = -Infinity
  for (const atom of atoms) {
    minX = Math.min(minX, atom.x)
    minY = Math.min(minY, atom.y)
    maxX = Math.max(maxX, atom.x)
    maxY = Math.max(maxY, atom.y)
  }
  const pad = 60
  const width = Math.max(maxX - minX, 1)
  const height = Math.max(maxY - minY, 1)
  const zoom = clampZoom(
    Math.min((size.value.w - 2 * pad) / width, (size.value.h - 2 * pad) / height),
  )
  state.view.value = {
    zoom,
    panX: size.value.w / 2 - ((minX + maxX) / 2) * zoom,
    panY: size.value.h / 2 - ((minY + maxY) / 2) * zoom,
  }
}

/** 100%: zoom 1, structure centroid (or scene origin) back to the middle. */
function resetView(): void {
  const atoms = state.snapshot.value.atoms
  let centre = { x: 0, y: 0 }
  if (atoms.length > 0) {
    let sumX = 0
    let sumY = 0
    for (const atom of atoms) {
      sumX += atom.x
      sumY += atom.y
    }
    centre = { x: sumX / atoms.length, y: sumY / atoms.length }
  }
  state.view.value = {
    zoom: 1,
    panX: size.value.w / 2 - centre.x,
    panY: size.value.h / 2 - centre.y,
  }
}

/** Step zoom about the canvas centre; zoomAt applies the 0.25–6 clamp. */
function zoomBy(factor: number): void {
  state.view.value = zoomAt(state.view.value, factor, size.value.w / 2, size.value.h / 2)
}

// ---------------------------------------------------------------------------
// Dispatch (MoleditPy mouseReleaseEvent matrix)
// ---------------------------------------------------------------------------

function handleClick(current: Press, release: Point): void {
  const tool = state.tool.value
  const snapshot = state.snapshot.value

  // Chains only appear via drag — a bare click changes nothing (the 0.4
  // tail guard lives in the commit path; see §12.2).
  if (tool === 'chain') return

  if (tool === 'select') {
    if (current.atomId !== null) {
      const id = current.atomId
      const selection = state.selection.value
      if (current.shift) {
        // Shift accumulates: toggle membership (community standard — see
        // the §12.8 deviation list; MoleditPy has no modifier branch).
        state.selection.value = selection.includes(id)
          ? selection.filter((other) => other !== id)
          : [...selection, id]
        state.selectedBond.value = null
      } else if (current.wasSelected) {
        // Second click on an already-selected atom releases it
        // (MoleditPy's was_selected_on_press → setSelected(False)).
        state.selection.value = selection.filter((other) => other !== id)
      } else {
        state.selection.value = [id]
        state.selectedBond.value = null
      }
      return
    }
    if (current.bond) {
      const { a1, a2 } = current.bond
      state.selection.value = []
      state.selectedBond.value = [a1, a2] as const
      return
    }
    if (!current.shift) state.clearSelection()
    return
  }

  if (tool === 'atom') {
    if (current.atomId !== null) {
      const target = atomById(snapshot, current.atomId)
      if (!target || target.symbol === state.symbol.value) return
      const id = current.atomId
      state.commit((s) => {
        const atom = atomById(s, id)
        if (atom) atom.symbol = state.symbol.value
      })
      return
    }
    state.commit((s) => addAtom(s, state.symbol.value, release.x, release.y))
    return
  }

  if (tool === 'bond') {
    if (current.bond) {
      const { a1, a2 } = current.bond
      const order = state.bondOrder.value
      const stereo = state.bondStereo.value
      state.commit((s) => {
        const bond = findBond(s, a1, a2)
        if (!bond) return
        if (stereo !== 0 && bond.order === order && bond.stereo === stereo) {
          // Same marker again flips the wedge/hash direction — the marker
          // must be able to point the other way (MoleditPy).
          const swapped = bond.a1
          bond.a1 = bond.a2
          bond.a2 = swapped
          return
        }
        // Clicking a bond writes the current tool settings; it never cycles
        // through orders (MoleditPy's bond-mode click).
        bond.order = order
        bond.stereo = stereo
      })
      return
    }
    // Short press on an atom is a no-op: bonds are drawn by dragging.
    if (current.atomId !== null) return
    // Bare click lays a single atom at the release point (MoleditPy's
    // create_atom — a drag is what makes the second atom + bond).
    state.commit((s) => addAtom(s, state.symbol.value, release.x, release.y))
    return
  }

  if (tool === 'erase') {
    if (current.atomId !== null) {
      const id = current.atomId
      state.commit((s) => removeAtom(s, id))
    } else if (current.bond) {
      const { a1, a2 } = current.bond
      state.commit((s) => removeBond(s, a1, a2))
    }
    return
  }

  if (tool === 'charge+' || tool === 'charge-') {
    if (current.atomId === null) return
    const step = tool === 'charge+' ? 1 : -1
    const id = current.atomId
    state.commit((s) => {
      const atom = atomById(s, id)
      if (atom) atom.charge = Math.max(-9, Math.min(9, atom.charge + step))
    })
    return
  }

  if (tool === 'radical') {
    if (current.atomId === null) return
    const id = current.atomId
    state.commit((s) => {
      const atom = atomById(s, id)
      if (atom) atom.radical = (atom.radical + 1) % 3
    })
    return
  }

  if (tool === 'template') {
    // The cursor rides into the plan so ghost and placement agree (15° aim
    // for atoms, cursor side for bonds).
    const target: RingTarget =
      current.atomId !== null
        ? { kind: 'atom', atomId: current.atomId, cursor: release }
        : current.bond
          ? { kind: 'bond', a1: current.bond.a1, a2: current.bond.a2, cursor: release }
          : { kind: 'free', centre: release }
    state.placeRing(target)
  }
}

/** Chain vertices for press→cursor: shared by the preview and the commit. */
function chainPlanFrom(
  current: Press,
  cursorScene: Point,
): { startAtomId: number | null; points: Point[]; snapId: number | null } | null {
  const snapshot = state.snapshot.value
  const startAtomId = current.atomId
  const startAtom = startAtomId !== null ? atomById(snapshot, startAtomId) : undefined
  if (startAtomId !== null && !startAtom) return null
  const start = startAtom ?? current.scene
  const { axisAngle, count } = chainAxes(start, cursorScene)
  const points = chainPoints(start, count, axisAngle)
  const radius = SNAP_PX / state.view.value.zoom
  const snapId = atomNear(snapshot, cursorScene, radius, startAtomId ?? undefined)
  if (snapId !== null) {
    const snapAtom = atomById(snapshot, snapId)
    if (snapAtom) {
      const end = points[points.length - 1]
      if (end) {
        end.x = snapAtom.x
        end.y = snapAtom.y
      }
    }
  }
  return { startAtomId, points, snapId }
}

function dragCreate(current: Press, endScene: Point): void {
  const tool = state.tool.value
  const snapshot = state.snapshot.value
  const radius = SNAP_PX / state.view.value.zoom
  const endAtomId = atomNear(snapshot, endScene, radius, current.atomId ?? undefined)
  const endPoint =
    endAtomId !== null
      ? (() => {
          const atom = atomById(snapshot, endAtomId)
          return atom ? { x: atom.x, y: atom.y } : endScene
        })()
      : endScene

  if (tool === 'chain') {
    const plan = chainPlanFrom(current, endScene)
    if (!plan || plan.points.length < 2) return
    state.commit((s) => {
      let previousId: number | null = plan.startAtomId
      const first = plan.points[0]
      if (previousId === null && first) {
        // The chain paints with the CURRENT element, not a hardcoded carbon
        // (MoleditPy commit_chain uses current_atom_symbol).
        previousId = addAtom(s, state.symbol.value, first.x, first.y).id
      }
      if (previousId === null) return
      for (let i = 1; i < plan.points.length; i++) {
        const point = plan.points[i]
        if (!point) continue
        const isLast = i === plan.points.length - 1
        const nextId =
          isLast && plan.snapId !== null
            ? plan.snapId
            : addAtom(s, state.symbol.value, point.x, point.y).id
        addBond(s, previousId, nextId, 1, 0)
        previousId = nextId
      }
    })
    return
  }

  // Grow one bond from an existing atom toward the release point: shared by
  // the bond-tool drag and the atom-tool drag-out so endpoint snapping lives
  // in exactly one place (task book B2, 单点提交约束).
  const growFrom = (fromId: number, order: 1 | 2 | 3, stereo: 0 | 1 | 2): void => {
    state.commit((s) => {
      if (endAtomId !== null) {
        addBond(s, fromId, endAtomId, order, stereo)
      } else {
        const created = addAtom(s, state.symbol.value, endPoint.x, endPoint.y)
        addBond(s, fromId, created.id, order, stereo)
      }
    })
  }

  if (tool === 'bond') {
    if (current.atomId !== null) {
      growFrom(current.atomId, state.bondOrder.value, state.bondStereo.value)
      return
    }
    state.commit((s) => {
      const first = addAtom(s, state.symbol.value, current.scene.x, current.scene.y)
      // Honour the same endpoint the rubber preview snapped to; laying a new
      // atom on top of an existing one would duplicate it invisibly.
      const secondId =
        endAtomId !== null ? endAtomId : addAtom(s, state.symbol.value, endPoint.x, endPoint.y).id
      addBond(s, first.id, secondId, state.bondOrder.value, state.bondStereo.value)
    })
    return
  }

  // Atom tool: press on an atom drags out a plain bond; press on empty space
  // still places two atoms and one bond (§4.3 three distinct paths).
  if (tool === 'atom') {
    if (current.atomId !== null) {
      growFrom(current.atomId, 1, 0)
      return
    }
    state.commit((s) => {
      const first = addAtom(s, state.symbol.value, current.scene.x, current.scene.y)
      const secondId =
        endAtomId !== null ? endAtomId : addAtom(s, state.symbol.value, endPoint.x, endPoint.y).id
      addBond(s, first.id, secondId, 1, 0)
    })
  }
}

function commitMove(atomId: number, delta: Point): void {
  const ids = state.selection.value.includes(atomId)
    ? [...state.selection.value]
    : [atomId]
  state.commit((s) => {
    for (const id of ids) {
      const atom = atomById(s, id)
      if (atom) {
        atom.x += delta.x
        atom.y += delta.y
      }
    }
  })
}

function selectBox(a: Point, b: Point): void {
  const minX = Math.min(a.x, b.x)
  const maxX = Math.max(a.x, b.x)
  const minY = Math.min(a.y, b.y)
  const maxY = Math.max(a.y, b.y)
  state.selection.value = state.snapshot.value.atoms
    .filter((atom) => atom.x >= minX && atom.x <= maxX && atom.y >= minY && atom.y <= maxY)
    .map((atom) => atom.id)
  state.selectedBond.value = null
}

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------

interface RenderBond {
  key: string
  /** Straight segments to draw (label-clipped; ring/parallel rules applied). */
  segments: [Point, Point][]
  /** Hash-bond cross ticks (stereo 2). */
  ticks: { x1: number; y1: number; x2: number; y2: number }[]
  wedge: string | null
  /** Clipped centre line — the hover highlight rides on it. */
  p1: Point
  p2: Point
  hovered: boolean
  selected: boolean
}

const movingIds = computed(() => {
  const atomId = dragKind.value === 'move' ? (press.value?.atomId ?? null) : null
  if (atomId === null) return new Set<number>()
  return state.selection.value.includes(atomId)
    ? new Set(state.selection.value)
    : new Set([atomId])
})

function positionOf(id: number): Point {
  const atom = atomById(state.snapshot.value, id)
  if (!atom) return { x: 0, y: 0 }
  const delta = movingIds.value.has(id) ? moveDelta.value : null
  return delta ? { x: atom.x + delta.x, y: atom.y + delta.y } : { x: atom.x, y: atom.y }
}

function unit(v: Point): Point {
  const len = Math.hypot(v.x, v.y)
  return len < 1e-9 ? { x: 0, y: 0 } : { x: v.x / len, y: v.y / len }
}

function awayDirection(snapshot: SketchSnapshot, id: number): Point {
  const self = atomById(snapshot, id)
  if (!self) return { x: 1, y: 0 }
  const bonds = bondsOf(snapshot, id)
  if (bonds.length === 0) return { x: 1, y: 0 }
  let sum = { x: 0, y: 0 }
  for (const bond of bonds) {
    const otherId = bond.a1 === id ? bond.a2 : bond.a1
    const other = atomById(snapshot, otherId)
    if (!other) continue
    const away = unit({ x: self.x - other.x, y: self.y - other.y })
    sum = { x: sum.x + away.x, y: sum.y + away.y }
  }
  const dir = unit(sum)
  return dir.x === 0 && dir.y === 0 ? { x: 1, y: 0 } : dir
}

function chargeText(charge: number): string {
  if (charge === 1) return '+'
  if (charge === -1) return '−'
  return `${Math.abs(charge)}${charge > 0 ? '+' : '−'}`
}

const renderedAtoms = computed(() => {
  const snapshot = state.snapshot.value
  const analysis = state.analysis.value
  // Hover feedback only while idle — never during a press.
  const hoverId = press.value === null ? state.pointer.value.atomId : null
  return snapshot.atoms.map((atom) => {
    const pos = positionOf(atom.id)
    const hidden = isSkeletonCarbon(snapshot, atom.id)
    const hCount = analysis?.implicitH[atom.id] ?? 0
    const away = awayDirection(snapshot, atom.id)
    const box = labelBox(atom.symbol)
    return {
      id: atom.id,
      symbol: atom.symbol,
      charge: atom.charge,
      radical: atom.radical,
      x: pos.x,
      y: pos.y,
      hidden,
      showH: !hidden && hCount > 0,
      hCount,
      hx: pos.x + away.x * 14,
      hy: pos.y + away.y * 14,
      // visual_rect = label background + 3 (MoleditPy).
      boxRx: box.rx + 3,
      boxRy: box.ry + 3,
      problem: analysis?.problems.includes(atom.id) ?? false,
      selected: state.selection.value.includes(atom.id),
      hovered: hoverId === atom.id,
    }
  })
})

const hoverBondKey = computed(() =>
  state.pointer.value.bond
    ? bondKey(state.pointer.value.bond[0], state.pointer.value.bond[1])
    : null,
)
const selectedBondKey = computed(() =>
  state.selectedBond.value
    ? bondKey(state.selectedBond.value[0], state.selectedBond.value[1])
    : null,
)

const renderedBonds = computed<RenderBond[]>(() => {
  const snapshot = state.snapshot.value
  const rings = state.analysis.value?.rings ?? []
  const hoverKey = press.value === null ? hoverBondKey.value : null
  const selectedKey = selectedBondKey.value
  const result: RenderBond[] = []
  for (const bond of snapshot.bonds) {
    const raw1 = positionOf(bond.a1)
    const raw2 = positionOf(bond.a2)
    // Clip against visible labels — closed-form of MoleditPy's 12-step
    // binary search so lines never run under a symbol.
    let t1 = 0
    let t2 = 1
    const atom1 = atomById(snapshot, bond.a1)
    if (atom1 && !isSkeletonCarbon(snapshot, bond.a1)) {
      const box = labelBox(atom1.symbol)
      t1 = ellipseExitT(raw1, raw2, raw1, box.rx, box.ry)
    }
    const atom2 = atomById(snapshot, bond.a2)
    if (atom2 && !isSkeletonCarbon(snapshot, bond.a2)) {
      const box = labelBox(atom2.symbol)
      t2 = 1 - ellipseExitT(raw2, raw1, raw2, box.rx, box.ry)
    }
    if (t1 >= t2) continue // both labels swallow the line — nothing to draw
    const at = (t: number): Point => ({
      x: raw1.x + (raw2.x - raw1.x) * t,
      y: raw1.y + (raw2.y - raw1.y) * t,
    })
    const p1 = at(t1)
    const p2 = at(t2)
    const key = bondKey(bond.a1, bond.a2)
    const base: RenderBond = {
      key,
      segments: [],
      ticks: [],
      wedge: null,
      p1,
      p2,
      hovered: hoverKey !== null && hoverKey === key,
      selected: selectedKey === key,
    }

    // Stereo markers only exist on single bonds (MoleditPy paint guard).
    if (bond.order === 1 && (bond.stereo === 1 || bond.stereo === 2)) {
      const rawLen = Math.hypot(raw2.x - raw1.x, raw2.y - raw1.y)
      // Marker window: both ends inset ≥5px from the atoms along the raw line.
      let w1 = rawLen > 0 ? Math.max(t1 * rawLen, 5) / rawLen : 0
      let w2 = rawLen > 0 ? Math.min(t2 * rawLen, rawLen - 5) / rawLen : 1
      if (w1 > w2) {
        w1 = 0.5
        w2 = 0.5
      }
      if (bond.stereo === 1) {
        const perp = unit({ x: -(raw2.y - raw1.y), y: raw2.x - raw1.x })
        const a = at(w1)
        const b = at(w2)
        const h1 = WEDGE_HALF * w1
        const h2 = WEDGE_HALF * w2
        base.wedge = [
          `${a.x - perp.x * h1},${a.y - perp.y * h1}`,
          `${a.x + perp.x * h1},${a.y + perp.y * h1}`,
          `${b.x + perp.x * h2},${b.y + perp.y * h2}`,
          `${b.x - perp.x * h2},${b.y - perp.y * h2}`,
        ].join(' ')
      } else {
        base.ticks = dashTicks(raw1, raw2, w1, w2)
      }
      result.push(base)
      continue
    }

    if (bond.order === 1) {
      base.segments = [[p1, p2]]
      result.push(base)
      continue
    }

    const perp = unit({ x: -(p2.y - p1.y), y: p2.x - p1.x })
    if (bond.order === 2) {
      const ring = rings.find((r) => r.atomIds.includes(bond.a1) && r.atomIds.includes(bond.a2))
      if (ring) {
        // Ring double: centre line + inner line translated 2×3.5px toward
        // the ring, shortened about its own midpoint by the interior angle.
        const ringCentre = { x: ring.center[0], y: ring.center[1] }
        const mid = { x: (p1.x + p2.x) / 2, y: (p1.y + p2.y) / 2 }
        const inward = { x: ringCentre.x - mid.x, y: ringCentre.y - mid.y }
        const sign = perp.x * inward.x + perp.y * inward.y >= 0 ? 1 : -1
        const shift = { x: perp.x * 7 * sign, y: perp.y * 7 * sign }
        const i1 = { x: p1.x + shift.x, y: p1.y + shift.y }
        const i2 = { x: p2.x + shift.x, y: p2.y + shift.y }
        const factor = ringDoubleShortenFactor(p1, p2, ringCentre)
        const innerCentre = { x: (i1.x + i2.x) / 2, y: (i1.y + i2.y) / 2 }
        base.segments = [
          [p1, p2],
          [
            { x: innerCentre.x + (i1.x - innerCentre.x) * factor, y: innerCentre.y + (i1.y - innerCentre.y) * factor },
            { x: innerCentre.x + (i2.x - innerCentre.x) * factor, y: innerCentre.y + (i2.y - innerCentre.y) * factor },
          ],
        ]
      } else {
        // Non-ring double: two parallels ±3.5, no centre line.
        base.segments = [
          [
            { x: p1.x + perp.x * 3.5, y: p1.y + perp.y * 3.5 },
            { x: p2.x + perp.x * 3.5, y: p2.y + perp.y * 3.5 },
          ],
          [
            { x: p1.x - perp.x * 3.5, y: p1.y - perp.y * 3.5 },
            { x: p2.x - perp.x * 3.5, y: p2.y - perp.y * 3.5 },
          ],
        ]
      }
      result.push(base)
      continue
    }

    // Triple: centred line + two side lines at ±3.5.
    base.segments = [
      [p1, p2],
      [
        { x: p1.x + perp.x * 3.5, y: p1.y + perp.y * 3.5 },
        { x: p2.x + perp.x * 3.5, y: p2.y + perp.y * 3.5 },
      ],
      [
        { x: p1.x - perp.x * 3.5, y: p1.y - perp.y * 3.5 },
        { x: p2.x - perp.x * 3.5, y: p2.y - perp.y * 3.5 },
      ],
    ]
    result.push(base)
  }
  return result
})

// ---------------------------------------------------------------------------
// Previews: rubber line, chain ghost, band, template ghost
// ---------------------------------------------------------------------------

const cursorScene = computed(() => state.pointer.value.scene)

const rubberAnchor = computed<Point | null>(() => {
  if (dragKind.value !== 'rubber' || !press.value) return null
  // The chain tool draws its own polyline instead of the single rubber line.
  if (state.tool.value === 'chain') return null
  if (press.value.atomId !== null) return positionOf(press.value.atomId)
  return press.value.scene
})

const rubberEnd = computed<Point | null>(() => {
  if (dragKind.value !== 'rubber' || !press.value || !cursorScene.value) return null
  const radius = SNAP_PX / state.view.value.zoom
  const snappedId = atomNear(
    state.snapshot.value,
    cursorScene.value,
    radius,
    press.value.atomId ?? undefined,
  )
  if (snappedId !== null) return positionOf(snappedId)
  return cursorScene.value
})

/** Zigzag polyline + bond count shown while the chain tool drags. */
const chainPreview = computed<{ points: Point[]; count: number; end: Point } | null>(() => {
  if (dragKind.value !== 'rubber' || state.tool.value !== 'chain') return null
  if (!press.value || !cursorScene.value) return null
  const plan = chainPlanFrom(press.value, cursorScene.value)
  if (!plan || plan.points.length < 2) return null
  const end = plan.points[plan.points.length - 1] ?? { x: 0, y: 0 }
  return { points: plan.points, count: plan.points.length - 1, end }
})

const bandRect = computed(() => {
  if (dragKind.value !== 'band' || !press.value || !cursorScene.value) return null
  const a = press.value.scene
  const b = cursorScene.value
  return {
    x: Math.min(a.x, b.x),
    y: Math.min(a.y, b.y),
    width: Math.abs(a.x - b.x),
    height: Math.abs(a.y - b.y),
  }
})

/** Live template ghost: the exact plan the next click would commit —
    MoleditPy's update_template_preview, computed on every pointer move. */
const templateGhost = computed(() => {
  if (state.tool.value !== 'template') return null
  const pointer = state.pointer.value
  if (pointer.scene === null) return null
  const snapshot = state.snapshot.value
  const target: RingTarget = altHeld.value
    ? { kind: 'free', centre: pointer.scene }
    : pointer.atomId !== null
      ? { kind: 'atom', atomId: pointer.atomId, cursor: pointer.scene }
      : pointer.bond
        ? { kind: 'bond', a1: pointer.bond[0], a2: pointer.bond[1], cursor: pointer.scene }
        : { kind: 'free', centre: pointer.scene }
  const plan = planRingFusion(snapshot, target, {
    size: state.templateSize.value,
    benzene: state.templateBenzene.value,
    symbols: state.templateSymbols.value ?? undefined,
  })
  if (!plan) return null

  const posOf = (ref: number): Point | null => {
    if (ref > 0) {
      const atom = atomById(snapshot, ref)
      return atom ? { x: atom.x, y: atom.y } : null
    }
    const created = plan.newAtoms[-ref - 1]
    return created ? { x: created.x, y: created.y } : null
  }

  interface GhostBond {
    key: string
    lines: [Point, Point][]
  }
  const bonds: GhostBond[] = []
  plan.newBonds.forEach((bond, index) => {
    const a = posOf(bond.a1)
    const b = posOf(bond.a2)
    if (!a || !b) return
    const dx = b.x - a.x
    const dy = b.y - a.y
    const len = Math.hypot(dx, dy)
    const perp =
      len < 1e-9 ? { x: 0, y: 0 } : { x: (-dy / len) * 3.5, y: (dx / len) * 3.5 }
    let lines: [Point, Point][]
    if (bond.order === 1) {
      lines = [[a, b]]
    } else if (bond.order === 2) {
      lines = [
        [{ x: a.x + perp.x, y: a.y + perp.y }, { x: b.x + perp.x, y: b.y + perp.y }],
        [{ x: a.x - perp.x, y: a.y - perp.y }, { x: b.x - perp.x, y: b.y - perp.y }],
      ]
    } else {
      lines = [
        [a, b],
        [{ x: a.x + perp.x, y: a.y + perp.y }, { x: b.x + perp.x, y: b.y + perp.y }],
        [{ x: a.x - perp.x, y: a.y - perp.y }, { x: b.x - perp.x, y: b.y - perp.y }],
      ]
    }
    bonds.push({ key: `gb${index}`, lines })
  })
  return {
    atoms: plan.newAtoms.map((atom, index) => ({
      key: `ga${index}`,
      x: atom.x,
      y: atom.y,
      symbol: atom.symbol,
    })),
    bonds,
  }
})
</script>

<template>
  <div ref="hostEl" class="sketch-canvas" :class="`sketch-canvas--${state.tool.value}`" data-test="sketch-canvas">
    <svg
      ref="svgEl"
      class="sketch-canvas__svg"
      :class="{
        'is-hit':
          state.pointer.value.atomId !== null || state.pointer.value.bond !== null,
      }"
      :viewBox="viewBox"
      @pointerdown="onPointerDown"
      @pointermove="onPointerMove"
      @pointerup="onPointerUp"
      @pointercancel="onPointerUp"
      @pointerleave="clearPointer"
      @contextmenu.prevent="onContextMenu"
      @dblclick="onDoubleClick"
      @wheel.prevent="onWheel"
    >
      <g class="sk-bonds">
        <g
          v-for="b in renderedBonds"
          :key="b.key"
          class="sk-bond"
          :class="{ 'is-hover': b.hovered, 'is-selected': b.selected }"
          :data-test="`bond-${b.key}`"
        >
          <polygon v-if="b.wedge" :points="b.wedge" class="sk-bond__wedge" />
          <template v-else>
            <line
              v-for="(seg, index) in b.segments"
              :key="index"
              :x1="seg[0].x"
              :y1="seg[0].y"
              :x2="seg[1].x"
              :y2="seg[1].y"
              class="sk-bond__line"
            />
            <line
              v-for="(tick, index) in b.ticks"
              :key="`t${index}`"
              :x1="tick.x1"
              :y1="tick.y1"
              :x2="tick.x2"
              :y2="tick.y2"
              class="sk-bond__tick"
            />
          </template>
          <line
            v-if="b.hovered && !b.selected"
            :x1="b.p1.x"
            :y1="b.p1.y"
            :x2="b.p2.x"
            :y2="b.p2.y"
            class="sk-bond__hl"
          />
        </g>
      </g>

      <g v-if="templateGhost" class="sk-ghost" data-test="sketch-template-ghost">
        <template v-for="b in templateGhost.bonds" :key="b.key">
          <line
            v-for="(line, index) in b.lines"
            :key="index"
            :x1="line[0].x"
            :y1="line[0].y"
            :x2="line[1].x"
            :y2="line[1].y"
            class="sk-ghost__line"
          />
        </template>
        <circle
          v-for="a in templateGhost.atoms"
          :key="a.key"
          :cx="a.x"
          :cy="a.y"
          r="5"
          class="sk-ghost__atom"
        />
      </g>

      <g class="sk-atoms">
        <g v-for="a in renderedAtoms" :key="a.id" class="sk-atom" :data-atom-id="a.id">
          <rect
            v-if="a.hovered"
            :x="a.x - a.boxRx"
            :y="a.y - a.boxRy"
            :width="a.boxRx * 2"
            :height="a.boxRy * 2"
            class="sk-atom__box sk-atom__box--hover"
          />
          <rect
            v-if="a.selected"
            :x="a.x - a.boxRx"
            :y="a.y - a.boxRy"
            :width="a.boxRx * 2"
            :height="a.boxRy * 2"
            class="sk-atom__box sk-atom__box--select"
          />
          <rect
            v-if="a.problem"
            :x="a.x - a.boxRx"
            :y="a.y - a.boxRy"
            :width="a.boxRx * 2"
            :height="a.boxRy * 2"
            class="sk-atom__box sk-atom__box--problem"
          />
          <text
            v-if="!a.hidden"
            :x="a.x"
            :y="a.y"
            class="sk-atom__label"
            text-anchor="middle"
            dominant-baseline="central"
          >
            {{ a.symbol
            }}<tspan
              v-if="a.charge !== 0"
              class="sk-atom__charge"
              dy="-0.45em"
              font-size="0.7em"
            >{{ chargeText(a.charge) }}</tspan
          >
          </text>
          <text
            v-if="a.showH"
            :x="a.hx"
            :y="a.hy"
            class="sk-atom__h"
            text-anchor="middle"
            dominant-baseline="central"
          >
            H<tspan v-if="a.hCount > 1" dy="0.32em" font-size="0.7em">{{ a.hCount }}</tspan>
          </text>
          <g v-if="a.radical > 0" class="sk-atom__radical">
            <circle v-if="a.radical === 1" :cx="a.x" :cy="a.y - 12" r="3" />
            <template v-else>
              <circle :cx="a.x - 5" :cy="a.y - 12" r="3" />
              <circle :cx="a.x + 5" :cy="a.y - 12" r="3" />
            </template>
          </g>
        </g>
      </g>

      <line
        v-if="rubberAnchor && rubberEnd"
        :x1="rubberAnchor.x"
        :y1="rubberAnchor.y"
        :x2="rubberEnd.x"
        :y2="rubberEnd.y"
        class="sk-rubber"
      />
      <g v-if="chainPreview" class="sk-chain-preview" data-test="sketch-chain-preview">
        <polyline
          class="sk-chain-line"
          fill="none"
          :points="chainPreview.points.map((p) => `${p.x},${p.y}`).join(' ')"
        />
        <text
          class="sk-chain-count"
          :x="chainPreview.end.x"
          :y="chainPreview.end.y - 14"
          text-anchor="middle"
        >n = {{ chainPreview.count }}</text>
      </g>
      <rect v-if="bandRect" v-bind="bandRect" class="sk-band" />
    </svg>
    <div v-if="!state.hasStructure.value" class="sketch-canvas__empty" data-test="sketch-empty">
      <div class="sketch-canvas__empty-title">{{ t('sketcher.emptyTitle') }}</div>
      <div class="sketch-canvas__empty-hint">{{ t('sketcher.emptyHint') }}</div>
    </div>
    <div class="sketch-canvas__views" data-test="sketch-views">
      <button
        type="button"
        class="sk-view"
        data-test="sketch-view-fit"
        :title="t('sketcher.viewFit')"
        @click="fitView"
      >
        ⤢
      </button>
      <button
        type="button"
        class="sk-view"
        data-test="sketch-view-reset"
        :title="t('sketcher.viewReset')"
        @click="resetView"
      >
        1:1
      </button>
      <button
        type="button"
        class="sk-view"
        data-test="sketch-view-zoom-in"
        :title="t('sketcher.viewZoomIn')"
        @click="zoomBy(1.25)"
      >
        ＋
      </button>
      <button
        type="button"
        class="sk-view"
        data-test="sketch-view-zoom-out"
        :title="t('sketcher.viewZoomOut')"
        @click="zoomBy(0.8)"
      >
        −
      </button>
    </div>
  </div>
</template>

<style scoped>
.sketch-canvas {
  position: relative;
  flex: 1;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  background:
    radial-gradient(circle at 1px 1px, var(--el-border-color-lighter) 1px, transparent 0)
      0 0 / 24px 24px;
}

.sketch-canvas__svg {
  display: block;
  width: 100%;
  height: 100%;
  touch-action: none;
  user-select: none;
}

.sketch-canvas--select .sketch-canvas__svg {
  cursor: default;
}

.sketch-canvas--atom .sketch-canvas__svg,
.sketch-canvas--bond .sketch-canvas__svg,
.sketch-canvas--charge\+ .sketch-canvas__svg,
.sketch-canvas--charge- .sketch-canvas__svg {
  cursor: crosshair;
}

.sketch-canvas--erase .sketch-canvas__svg {
  cursor: not-allowed;
}

/* After the per-tool rules (equal specificity → source order wins): a hit
   under the pointer invites a click. */
.sketch-canvas__svg.is-hit {
  cursor: pointer;
}

.sk-bond__line,
.sk-bond__wedge {
  stroke: var(--el-text-color-regular);
  stroke-width: 2;
  stroke-linecap: round;
  pointer-events: none;
}

.sk-bond__wedge {
  fill: var(--el-text-color-regular);
  stroke: none;
}

/* Hash bond: ladder of cross ticks, thinner than the body lines. */
.sk-bond__tick {
  stroke: var(--el-text-color-regular);
  stroke-width: 2.5;
  stroke-linecap: round;
  pointer-events: none;
}

/* MoleditPy HOVER_PEN_WIDTH=8 LightGreen overlay on the clipped line. */
.sk-bond__hl {
  stroke: rgb(144 238 144 / 70%);
  stroke-width: 8;
  stroke-linecap: round;
  pointer-events: none;
}

.sk-bond.is-selected .sk-bond__line {
  stroke: rgb(0 100 255);
  stroke-width: 3;
}

.sk-bond.is-selected .sk-bond__wedge {
  fill: rgb(0 100 255);
}

.sk-bond.is-selected .sk-bond__tick {
  stroke: rgb(0 100 255);
  stroke-width: 3;
}

.sk-atom__label,
.sk-atom__h {
  fill: var(--el-text-color-regular);
  /* MoleditPy ships Arial 22 Bold; 19 keeps our layout balanced (§12.8). */
  font-size: 19px;
  font-weight: 700;
  pointer-events: none;
}

.sk-atom__charge {
  fill: currentColor;
}

.sk-atom__radical circle {
  fill: currentColor;
  pointer-events: none;
}

.sk-atom__box {
  fill: none;
  pointer-events: none;
}

/* MoleditPy highlight colours: lightgreen hover, blue select, red problem. */
.sk-atom__box--hover {
  stroke: rgb(144 238 144 / 78%);
  stroke-width: 3;
  stroke-linejoin: round;
}

.sk-atom__box--select {
  stroke: rgb(0 100 255);
  stroke-width: 3;
}

.sk-atom__box--problem {
  stroke: rgb(255 0 0 / 78%);
  stroke-width: 4;
}

/* Temp line: Qt's red dotted pen — armed at press for bond/atom/chain. */
.sk-rubber {
  stroke: var(--el-color-danger);
  stroke-width: 2;
  stroke-dasharray: 0.01 6;
  stroke-linecap: round;
  pointer-events: none;
}

.sk-chain-line {
  stroke: var(--el-text-color-secondary);
  stroke-width: 2;
  stroke-dasharray: 6 4;
  stroke-linecap: round;
  pointer-events: none;
}

.sk-chain-count {
  fill: var(--el-text-color-secondary);
  font-size: 12px;
  font-weight: 600;
  pointer-events: none;
}

.sk-ghost__line {
  stroke: var(--el-color-primary);
  stroke-width: 2;
  stroke-linecap: round;
  opacity: 0.5;
  pointer-events: none;
}

.sk-ghost__atom {
  fill: var(--el-color-primary);
  opacity: 0.45;
  pointer-events: none;
}

.sk-band {
  fill: var(--el-color-primary);
  fill-opacity: 0.1;
  stroke: var(--el-color-primary);
  stroke-width: 1;
  stroke-dasharray: 5 4;
  pointer-events: none;
}

.sketch-canvas__empty {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
  align-items: center;
  justify-content: center;
  pointer-events: none;
}

.sketch-canvas__empty-title {
  font-size: 15px;
  color: var(--el-text-color-secondary);
}

.sketch-canvas__empty-hint {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}

.sketch-canvas__views {
  position: absolute;
  right: 12px;
  bottom: 12px;
  display: flex;
  gap: 4px;
}

.sk-view {
  box-sizing: border-box;
  min-width: 28px;
  height: 26px;
  margin: 0;
  padding: 0 6px;
  font: inherit;
  font-size: 13px;
  line-height: 1;
  color: var(--el-text-color-regular);
  cursor: pointer;
  background: var(--el-bg-color-overlay);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  box-shadow: var(--el-box-shadow-light);
}

.sk-view:hover {
  color: var(--el-color-primary);
  border-color: var(--el-color-primary-light-5);
}
</style>
