/** Geometry for the sketcher: coordinates, snapping, placement rules.

    Screen = scene * zoom + pan.  Distances quoted in *screen* pixels (14 px
    hit/snap radius) are converted with /zoom at the point of use so the feel
    does not change when the user zooms (task book §2.2).
*/

import {
  atomById,
  bondsOf,
  findBond,
  type SketchAtom,
  type SketchSnapshot,
} from './model'

/** 75 px per bond = 1.5 A — keep in sync with core/chem/sketch.py. */
export const ANGSTROM_PER_PX = 0.02
export const BOND_PX = 75
/** Hit/snap radius in screen pixels at zoom 1. */
export const SNAP_PX = 14
/** Pointer travel before a press becomes a drag: Qt's startDragDistance —
    below it a release is a click (MoleditPy `is_click`). */
export const DRAG_THRESHOLD_PX = 10
/** Wedge/dash half-width at the far end of a stereo bond (MoleditPy). */
export const WEDGE_HALF = 8
/** Cross ticks on a hash bond: t = i / DASH_TICKS for i = 1..count. */
export const DASH_TICKS = 8

export interface Point {
  x: number
  y: number
}

export interface View {
  zoom: number
  panX: number
  panY: number
}

export function clampZoom(zoom: number): number {
  return Math.min(6, Math.max(0.25, zoom))
}

export function screenToScene(px: number, py: number, view: View): Point {
  return { x: (px - view.panX) / view.zoom, y: (py - view.panY) / view.zoom }
}

/** Zoom keeping the scene point under the cursor fixed. */
export function zoomAt(view: View, factor: number, screenX: number, screenY: number): View {
  const zoom = clampZoom(view.zoom * factor)
  const sceneX = (screenX - view.panX) / view.zoom
  const sceneY = (screenY - view.panY) / view.zoom
  return { zoom, panX: screenX - sceneX * zoom, panY: screenY - sceneY * zoom }
}

export function distance(a: Point, b: Point): number {
  return Math.hypot(a.x - b.x, a.y - b.y)
}

function subtract(a: Point, b: Point): Point {
  return { x: a.x - b.x, y: a.y - b.y }
}

function length(v: Point): number {
  return Math.hypot(v.x, v.y)
}

function normalize(v: Point): Point {
  const size = length(v)
  return size < 1e-9 ? { x: 0, y: 0 } : { x: v.x / size, y: v.y / size }
}

/** Nearest atom within radiusScene, excluding `excludeId` (never snap to self). */
export function atomNear(
  snapshot: SketchSnapshot,
  point: Point,
  radiusScene: number,
  excludeId?: number,
): number | null {
  let best: number | null = null
  let bestDistance = radiusScene
  for (const atom of snapshot.atoms) {
    if (atom.id === excludeId) continue
    const d = distance(point, atom)
    if (d <= bestDistance) {
      best = atom.id
      bestDistance = d
    }
  }
  return best
}

export function pointSegmentDistance(p: Point, a: Point, b: Point): number {
  const ab = subtract(b, a)
  const denom = ab.x * ab.x + ab.y * ab.y
  if (denom < 1e-9) return distance(p, a)
  let t = ((p.x - a.x) * ab.x + (p.y - a.y) * ab.y) / denom
  t = Math.min(1, Math.max(0, t))
  return distance(p, { x: a.x + t * ab.x, y: a.y + t * ab.y })
}

/** Nearest bond within radiusScene (atoms win ties — canvas hits atoms first). */
export function bondNear(
  snapshot: SketchSnapshot,
  point: Point,
  radiusScene: number,
): { a1: number; a2: number } | null {
  let best: { a1: number; a2: number } | null = null
  let bestDistance = radiusScene
  for (const bond of snapshot.bonds) {
    const from = atomById(snapshot, bond.a1)
    const to = atomById(snapshot, bond.a2)
    if (!from || !to) continue
    const d = pointSegmentDistance(point, from, to)
    if (d <= bestDistance) {
      best = { a1: bond.a1, a2: bond.a2 }
      bestDistance = d
    }
  }
  return best
}

export interface PlacementOptions {
  /** Order of the bond about to be created: triple continues straight. */
  targetOrder?: 1 | 2 | 3
  /** Zigzag side for the 1-neighbour case; MoleditPy flips it after each
      placement, so digit sequences walk the chain the way chemists draw it. */
  clockwise?: boolean
}

/** Free angle for the next bond at `fromId` (MoleditPy
    `_calculate_new_atom_position` — the community zigzag rules). */
export function nextPlacement(
  snapshot: SketchSnapshot,
  fromId: number,
  options: PlacementOptions = {},
): Point | null {
  const from = atomById(snapshot, fromId)
  if (!from) return null
  // Explicit hydrogens never steer the geometry (MoleditPy ignores them too).
  const bonds = bondsOf(snapshot, fromId).filter((bond) => {
    const otherId = bond.a1 === fromId ? bond.a2 : bond.a1
    return atomById(snapshot, otherId)?.symbol !== 'H'
  })

  // No neighbours: straight up (the canvas grows downward, chemistry does not).
  if (bonds.length === 0) return { x: from.x, y: from.y - BOND_PX }

  if (bonds.length === 1) {
    const first = bonds[0]
    if (!first) return null
    const neighborId = first.a1 === fromId ? first.a2 : first.a1
    const neighbor = atomById(snapshot, neighborId)
    if (!neighbor) return null
    const base = Math.atan2(from.y - neighbor.y, from.x - neighbor.x)
    // Triple (either end) continues straight — the linear alkyne convention;
    // otherwise ±60° from the incoming bond gives the 120° zigzag.
    const straight = options.targetOrder === 3 || first.order === 3
    const clockwise = options.clockwise ?? true
    const angle = straight ? base : base + (clockwise ? Math.PI / 3 : -Math.PI / 3)
    return { x: from.x + Math.cos(angle) * BOND_PX, y: from.y + Math.sin(angle) * BOND_PX }
  }

  // ≥2 neighbours: opposite the sum of unit bond vectors.  `from − other`
  // is already that opposite, so no second negation — negating again would
  // aim straight back into the crowded side.  Degenerate sums (symmetric
  // stars) have no defined direction; the tolerances mirror MoleditPy
  // (0.1 for the tripod, 0.01 otherwise).
  let sum = { x: 0, y: 0 }
  for (const bond of bonds) {
    const otherId = bond.a1 === fromId ? bond.a2 : bond.a1
    const other = atomById(snapshot, otherId)
    if (!other) continue
    const unit = normalize(subtract(from, other))
    sum = { x: sum.x + unit.x, y: sum.y + unit.y }
  }
  const manhattan = Math.abs(sum.x) + Math.abs(sum.y)
  if (bonds.length === 3) {
    if (manhattan > 0.1) {
      const direction = normalize(sum)
      return { x: from.x + direction.x * BOND_PX, y: from.y + direction.y * BOND_PX }
    }
    // Symmetric tripod: fall back to the up-right diagonal.
    return { x: from.x + BOND_PX * 0.7071, y: from.y - BOND_PX * 0.7071 }
  }
  if (manhattan > 0.01) {
    const direction = normalize(sum)
    return { x: from.x + direction.x * BOND_PX, y: from.y + direction.y * BOND_PX }
  }
  return { x: from.x, y: from.y - BOND_PX }
}

/** Scene position offset from `origin` used to start a drag placed two atoms. */
export function pointAtAngle(origin: Point, angle: number): Point {
  return { x: origin.x + Math.cos(angle) * BOND_PX, y: origin.y + Math.sin(angle) * BOND_PX }
}

// ---------------------------------------------------------------------------
// Label clipping, stereo geometry, ghost rings (MoleditPy drawing rules)
// ---------------------------------------------------------------------------

/** Round an angle to the nearest 15° (MoleditPy ghost-ring aim). */
export function snap15deg(angle: number): number {
  const step = Math.PI / 12
  return Math.round(angle / step) * step
}

/** Half-extents of the label background ellipse = text + MoleditPy's
    (-5, -8, +5, +8) pad.  Bond lines are clipped against this ellipse so
    they never run under a visible symbol; skeleton carbons skip the clip. */
export function labelBox(symbol: string): { rx: number; ry: number } {
  return { rx: 6 * symbol.length + 5, ry: 13 }
}

/** Parameter t along `from→to` where the segment EXITS the ellipse centred
    at `from` (0 when the start is already outside) — the closed-form stand-in
    for MoleditPy's 12-step binary search against the label path. */
export function ellipseExitT(
  from: Point,
  to: Point,
  centre: Point,
  rx: number,
  ry: number,
): number {
  const ux = (from.x - centre.x) / rx
  const uy = (from.y - centre.y) / ry
  if (ux * ux + uy * uy > 1) return 0
  const dx = (to.x - from.x) / rx
  const dy = (to.y - from.y) / ry
  const a = dx * dx + dy * dy
  if (a < 1e-12) return 0
  const b = 2 * (ux * dx + uy * dy)
  const c = ux * ux + uy * uy - 1
  const disc = b * b - 4 * a * c
  if (disc < 0) return 0
  // Exit root: the positive solution when starting inside.
  return Math.min(1, Math.max(0, (-b + Math.sqrt(disc)) / (2 * a)))
}

/** Length factor for the inner line of a ring double bond: bonds facing a
    sharp ring angle shorten more (benzene 0.8), wide angles keep more. */
export function ringDoubleShortenFactor(p1: Point, p2: Point, ringCentre: Point): number {
  const angleAt = (towardBond: Point, towardRing: Point): number | null => {
    const l1 = length(towardBond)
    const l2 = length(towardRing)
    if (l1 <= 1e-6 || l2 <= 1e-6) return null
    const cos =
      (towardBond.x * towardRing.x + towardBond.y * towardRing.y) / (l1 * l2)
    return Math.acos(Math.min(1, Math.max(-1, cos)))
  }
  const interior: number[] = []
  const h1 = angleAt(subtract(p2, p1), subtract(ringCentre, p1))
  const h2 = angleAt(subtract(p1, p2), subtract(ringCentre, p2))
  if (h1 !== null) interior.push(2 * h1)
  if (h2 !== null) interior.push(2 * h2)
  if (interior.length === 0) return 0.8
  const ringAngle = interior.reduce((sum, value) => sum + value, 0) / interior.length
  const benzene = (2 * Math.PI) / 3
  const cyclopropene = Math.PI / 3
  if (ringAngle <= benzene) {
    const sharpness = Math.min(1, Math.max(0, (benzene - ringAngle) / (benzene - cyclopropene)))
    return Math.max(0.55, 0.8 - 0.25 * sharpness)
  }
  const openness = Math.min(1, Math.max(0, (ringAngle - benzene) / (Math.PI - benzene)))
  return Math.min(0.9, 0.8 + 0.1 * openness)
}

/** Hash-bond cross ticks: at t = i/count of the RAW line (only the ones
    inside the visible [t1, t2] window), half-width = WEDGE_HALF·t — the
    growing ladder MoleditPy draws instead of a uniform dash pattern. */
export function dashTicks(
  raw1: Point,
  raw2: Point,
  t1: number,
  t2: number,
  count = DASH_TICKS,
): { x1: number; y1: number; x2: number; y2: number }[] {
  const dx = raw2.x - raw1.x
  const dy = raw2.y - raw1.y
  const len = Math.hypot(dx, dy)
  if (len < 1e-9) return []
  const nx = -dy / len
  const ny = dx / len
  const ticks: { x1: number; y1: number; x2: number; y2: number }[] = []
  for (let i = 1; i <= count; i++) {
    const t = i / count
    if (t < t1 || t > t2) continue
    const cx = raw1.x + dx * t
    const cy = raw1.y + dy * t
    const w = WEDGE_HALF * t
    ticks.push({ x1: cx - nx * w, y1: cy - ny * w, x2: cx + nx * w, y2: cy + ny * w })
  }
  return ticks
}

/** Regular n-gon whose first edge runs p0→p1 (MoleditPy
    `_calculate_polygon_from_edge`: rotate the edge by the exterior angle
    n-2 times).  `useExistingLength` keeps the given edge (bond fusion);
    otherwise the edge normalises to BOND_PX (atom aim).  With `cursor`, the
    polygon flips to the cursor side of the edge — but the atom-aim call site
    deliberately omits it, matching MoleditPy's fixed-face ghost. */
export function polygonFromEdge(
  p0: Point,
  p1: Point,
  n: number,
  options: { cursor?: Point; useExistingLength?: boolean } = {},
): Point[] {
  if (n < 3) return []
  let vx = p1.x - p0.x
  let vy = p1.y - p0.y
  const edgeLength = Math.hypot(vx, vy)
  if (edgeLength < 1e-9) return []
  const targetLength = options.useExistingLength ? edgeLength : BOND_PX
  vx = (vx / edgeLength) * targetLength
  vy = (vy / edgeLength) * targetLength
  const second = { x: p0.x + vx, y: p0.y + vy }
  const points: Point[] = [{ x: p0.x, y: p0.y }, second]
  const interior = ((n - 2) * Math.PI) / n
  let rotation = Math.PI - interior
  if (options.cursor) {
    // cross(edge, cursor − p0) < 0 means the fixed face points away from the
    // cursor; negating the rotation lands the polygon on the cursor side.
    const cross = vx * (options.cursor.y - p0.y) - vy * (options.cursor.x - p0.x)
    if (cross < 0) rotation = -rotation
  }
  const cos = Math.cos(rotation)
  const sin = Math.sin(rotation)
  let ex = vx
  let ey = vy
  let px = second.x
  let py = second.y
  for (let i = 0; i < n - 2; i++) {
    const nx = ex * cos - ey * sin
    const ny = ex * sin + ey * cos
    ex = nx
    ey = ny
    px += ex
    py += ey
    points.push({ x: px, y: py })
  }
  return points
}

export function atomPositionWithDelta(
  atom: SketchAtom,
  delta: Point | null,
): { x: number; y: number } {
  return delta ? { x: atom.x + delta.x, y: atom.y + delta.y } : { x: atom.x, y: atom.y }
}

// ---------------------------------------------------------------------------
// Ring templates (task book 4.4)
// ---------------------------------------------------------------------------

export interface RingTemplateSpec {
  size: number
  /** Kekulé alternation (single/double alternation); false = all-single. */
  benzene: boolean
  /** Vertex symbols, index = vertex 0..n-1 (vertex 0 = top on free placement).
      Shared vertices keep the existing atom's symbol — only NEW atoms take
      template symbols (task book 26 §9). Absent = all carbon. */
  symbols?: string[]
}

export type RingTarget =
  | { kind: 'free'; centre: Point }
  /** `cursor` aims the first edge (MoleditPy ghost); absent = free-side rule. */
  | { kind: 'atom'; atomId: number; cursor?: Point }
  | { kind: 'bond'; a1: number; a2: number; cursor?: Point }

export interface RingPlan {
  /** New carbon atoms; a negative reference -(index + 1) in `newBonds` addresses one. */
  newAtoms: { symbol: string; x: number; y: number }[]
  /** a1/a2: positive = existing atom id, negative = -(newIndex + 1). */
  newBonds: { a1: number; a2: number; order: 1 | 2 | 3 }[]
}

/** Best-effort upper bounds for the fusion downgrade; unknown elements pass through. */
const MAX_VALENCE: Record<string, number> = {
  H: 1,
  B: 3,
  C: 4,
  N: 3,
  O: 2,
  F: 1,
  Si: 4,
  P: 5,
  S: 6,
  Cl: 1,
  Br: 1,
  I: 1,
}

/** Side length → circumradius of a regular polygon member. */
function ringRadius(size: number, side: number): number {
  return side / (2 * Math.sin(Math.PI / size))
}

function normalizeAngle(angle: number): number {
  let a = angle
  while (a > Math.PI) a -= 2 * Math.PI
  while (a <= -Math.PI) a += 2 * Math.PI
  return a
}

function polygonVertices(
  centre: Point,
  radius: number,
  size: number,
  startAngle: number,
  step: number,
): Point[] {
  const vertices: Point[] = []
  for (let k = 0; k < size; k++) {
    const angle = startAngle + step * k
    vertices.push({ x: centre.x + radius * Math.cos(angle), y: centre.y + radius * Math.sin(angle) })
  }
  return vertices
}

/** Existing bond-order sum for an atom (both already-drawn and planned bonds). */
function valenceAt(
  snapshot: SketchSnapshot,
  running: Map<number, number>,
  ref: number,
): number {
  const known = running.get(ref)
  if (known !== undefined) return known
  if (ref < 0) return 0
  let sum = 0
  for (const bond of snapshot.bonds) {
    if (bond.a1 === ref || bond.a2 === ref) sum += bond.order
  }
  return sum
}

/** Place a template ring; null when the size is out of range or a hit atom vanished mid-flight. */
export function planRingFusion(
  snapshot: SketchSnapshot,
  target: RingTarget,
  template: RingTemplateSpec,
): RingPlan | null {
  const n = template.size
  if (!Number.isInteger(n) || n < 3 || n > 9) return null

  let centre: Point | null = null
  let step = (2 * Math.PI) / n
  let startAngle = -Math.PI / 2
  let sideLength = BOND_PX
  let vertices: Point[] | null = null
  const shared = new Map<number, number>()
  let sharedEdgeStart = -1

  if (target.kind === 'bond') {
    const a1 = atomById(snapshot, target.a1)
    const a2 = atomById(snapshot, target.a2)
    if (!a1 || !a2) return null
    const edgeLength = distance(a1, a2)
    // A collapsed edge has no stable side to build on; treat it as a click on
    // empty space instead of emitting a zero-area polygon.
    if (edgeLength < SNAP_PX) {
      return planRingFusion(
        snapshot,
        { kind: 'free', centre: { x: (a1.x + a2.x) / 2, y: (a1.y + a2.y) / 2 } },
        template,
      )
    }
    sideLength = edgeLength
    if (target.cursor) {
      // MoleditPy bond ghost: the ring hugs the cursor side of the shared
      // edge, keeping the edge's own length.
      vertices = polygonFromEdge(a1, a2, n, {
        cursor: target.cursor,
        useExistingLength: true,
      })
      if (vertices.length === 0) return null
    } else {
      const radius = ringRadius(n, edgeLength)
      const ux = (a2.x - a1.x) / edgeLength
      const uy = (a2.y - a1.y) / edgeLength
      const apothem = radius * Math.cos(Math.PI / n)
      const mid = { x: (a1.x + a2.x) / 2, y: (a1.y + a2.y) / 2 }
      // Grow the new ring away from the existing structure: the side whose
      // circumcircle swallows fewer drawn atoms is the free side.
      const others = snapshot.atoms.filter((atom) => atom.id !== a1.id && atom.id !== a2.id)
      const score = (candidate: Point) =>
        others.filter((atom) => distance(candidate, atom) < radius).length
      const sideA = { x: mid.x - uy * apothem, y: mid.y + ux * apothem }
      const sideB = { x: mid.x + uy * apothem, y: mid.y - ux * apothem }
      centre = score(sideA) <= score(sideB) ? sideA : sideB
      startAngle = Math.atan2(a1.y - centre.y, a1.x - centre.x)
      step = normalizeAngle(Math.atan2(a2.y - centre.y, a2.x - centre.x) - startAngle)
    }
    shared.set(0, a1.id)
    shared.set(1, a2.id)
    sharedEdgeStart = 0
  } else if (target.kind === 'atom') {
    const atom = atomById(snapshot, target.atomId)
    if (!atom) return null
    if (target.cursor) {
      // MoleditPy ghost: the first edge leaves the atom toward the cursor,
      // snapped to 15°, and the polygon trails on a fixed face (no cursor
      // flip — p0/p1 already carry the aim).
      const angle = snap15deg(
        Math.atan2(target.cursor.y - atom.y, target.cursor.x - atom.x),
      )
      const tip = {
        x: atom.x + Math.cos(angle) * BOND_PX,
        y: atom.y + Math.sin(angle) * BOND_PX,
      }
      vertices = polygonFromEdge(atom, tip, n)
      if (vertices.length === 0) return null
    } else {
      const radius = ringRadius(n, BOND_PX)
      // Suspend the ring on the atom's free side: opposite the sum of the
      // vectors pointing at its current neighbours (same rule as nextPlacement).
      let sum = { x: 0, y: 0 }
      for (const bond of bondsOf(snapshot, atom.id)) {
        const otherId = bond.a1 === atom.id ? bond.a2 : bond.a1
        const other = atomById(snapshot, otherId)
        if (!other) continue
        sum = { x: sum.x + (atom.x - other.x), y: sum.y + (atom.y - other.y) }
      }
      let direction = normalize(sum)
      if (length(direction) < 1e-6) direction = { x: 0, y: -1 }
      centre = { x: atom.x + direction.x * radius, y: atom.y + direction.y * radius }
      startAngle = Math.atan2(atom.y - centre.y, atom.x - centre.x)
    }
    shared.set(0, atom.id)
  } else {
    // Free placement: odd rings hang a vertex at the top, even rings a flat
    // top edge (MoleditPy's −π/2 vs −π/2 − step/2 start).
    step = (2 * Math.PI) / n
    startAngle = n % 2 !== 0 ? -Math.PI / 2 : -Math.PI / 2 - step / 2
    centre = target.centre
  }

  if (!vertices) {
    if (!centre) return null // unreachable: every branch sets vertices or centre
    vertices = polygonVertices(centre, ringRadius(n, sideLength), n, startAngle, step)
  }

  // Kekulé alternation anchored on the shared edge for fused benzene; fresh
  // rings start with a single bond. The 5-membered aromatic hetero templates
  // (pyrrole/furan/thiophene) alternate too: [1,2,1,2,1] leaves the hetero at
  // vertex 0 with two single bonds, which is the correct Kekulé form.
  const sharedBond =
    target.kind === 'bond' ? findBond(snapshot, target.a1, target.a2) : undefined
  const anchor = sharedBond && (sharedBond.order === 1 || sharedBond.order === 2) ? sharedBond.order : 1
  const orders: number[] = []
  for (let k = 0; k < n; k++) {
    if (!template.benzene) orders.push(1)
    else if (target.kind === 'bond') orders.push(k % 2 === 0 ? anchor : 3 - anchor)
    else orders.push(k % 2 === 0 ? 1 : 2)
  }

  const newAtoms: RingPlan['newAtoms'] = []
  const refs = new Map<number, number>()
  for (let k = 0; k < n; k++) {
    const existingId = shared.get(k)
    if (existingId !== undefined) {
      refs.set(k, existingId)
      continue
    }
    const vertex = vertices[k]
    if (!vertex) continue
    refs.set(k, -(newAtoms.length + 1))
    newAtoms.push({ symbol: template.symbols?.[k] ?? 'C', x: vertex.x, y: vertex.y })
  }

  const planned: RingPlan['newBonds'] = []
  for (let k = 0; k < n; k++) {
    // The shared edge keeps the order it was drawn with (task book 4.4).
    if (k === sharedEdgeStart) continue
    const a1 = refs.get(k)
    const a2 = refs.get((k + 1) % n)
    if (a1 === undefined || a2 === undefined) continue
    planned.push({ a1, a2, order: orders[k] as 1 | 2 | 3 })
  }

  // Downgrade NEW bonds only, until every touched atom fits its valence:
  // drawn bonds stay exactly as the user made them.  New-atom symbols come
  // from the plan itself so a template N/O/S downgrades against N=3/O=2.
  const running = new Map<number, number>()
  const symbolOf = (ref: number) =>
    ref > 0 ? (atomById(snapshot, ref)?.symbol ?? '') : (newAtoms[-ref - 1]?.symbol ?? 'C')
  const newBonds = planned.map((bond) => {
    let order = bond.order
    for (const ref of [bond.a1, bond.a2]) {
      const max = MAX_VALENCE[symbolOf(ref)]
      if (max === undefined) continue
      const allowed = Math.max(1, max - valenceAt(snapshot, running, ref))
      // order > allowed implies allowed ≤ 2 here, so the cast is sound.
      if (order > allowed) order = allowed as 1 | 2 | 3
    }
    running.set(bond.a1, valenceAt(snapshot, running, bond.a1) + order)
    running.set(bond.a2, valenceAt(snapshot, running, bond.a2) + order)
    return { ...bond, order: order as 1 | 2 | 3 }
  })

  return { newAtoms, newBonds }
}

// ---------------------------------------------------------------------------
// Chain tool (task book 4.3): drag a zigzag alkyl chain along a snapped axis
// ---------------------------------------------------------------------------

/** Zigzag half-angle from the chain axis (30°). */
export const CHAIN_HALF_ANGLE = Math.PI / 6
/** Chain axis snaps every 15°. */
export const CHAIN_AXIS_STEP = Math.PI / 12
/** Guard against absurd projections (≈3000 px of chain). */
export const CHAIN_MAX_BONDS = 40

/** One zigzag bond projects BOND_PX·cos30° onto the axis. */
export const CHAIN_PROJECTION = BOND_PX * Math.cos(CHAIN_HALF_ANGLE)

export interface ChainAxes {
  axisAngle: number
  count: number
}

/** Snapped axis + bond count from the drag projection (task book 4.3). */
export function chainAxes(start: Point, cursor: Point): ChainAxes {
  const dx = cursor.x - start.x
  const dy = cursor.y - start.y
  const axisAngle = Math.round(Math.atan2(dy, dx) / CHAIN_AXIS_STEP) * CHAIN_AXIS_STEP
  const projection = dx * Math.cos(axisAngle) + dy * Math.sin(axisAngle)
  const exact = projection / CHAIN_PROJECTION
  let count = Math.floor(exact)
  // Keep a tail bond only when it reaches 0.4 of a bond — below that the
  // chain looks collapsed into the previous vertex (task book 4.3).
  if (exact - count >= 0.4) count += 1
  count = Math.max(1, Math.min(CHAIN_MAX_BONDS, count))
  return { axisAngle, count }
}

/** Zigzag vertices P0..Pk; bond i runs at axis ±30°, alternating each step. */
export function chainPoints(start: Point, count: number, axisAngle: number): Point[] {
  const points: Point[] = [{ x: start.x, y: start.y }]
  let current = { x: start.x, y: start.y }
  for (let i = 1; i <= count; i++) {
    const angle = axisAngle + (i % 2 === 1 ? -CHAIN_HALF_ANGLE : CHAIN_HALF_ANGLE)
    current = {
      x: current.x + BOND_PX * Math.cos(angle),
      y: current.y + BOND_PX * Math.sin(angle),
    }
    points.push(current)
  }
  return points
}
