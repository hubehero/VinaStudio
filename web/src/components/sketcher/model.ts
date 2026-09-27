/** Graph data for the 2D sketcher: pure operations, no rendering, no Vue.

    The snapshot is the unit of undo: every mutation runs through
    `state.commit`, which clones before touching and pushes the clone onto the
    history stack.  Structured-clone-safe plain data only.
*/

export interface SketchAtom {
  id: number
  symbol: string
  /** Scene pixels; y grows downward (screen space). */
  x: number
  y: number
  charge: number
  radical: number
}

export interface SketchBond {
  a1: number
  a2: number
  /** Kekule order; the drawing tools emit 1 | 2 | 3. */
  order: 1 | 2 | 3
  /** 0 none, 1 wedge, 2 hash — drawn at the a1 end. */
  stereo: 0 | 1 | 2
}

export interface SketchSnapshot {
  atoms: SketchAtom[]
  bonds: SketchBond[]
  nextId: number
}

export function emptySnapshot(): SketchSnapshot {
  return { atoms: [], bonds: [], nextId: 1 }
}

export function cloneSnapshot(snapshot: SketchSnapshot): SketchSnapshot {
  // The live snapshot is a Vue reactive Proxy; V8's native clone rejects
  // Proxies with DataCloneError, which would silently kill every commit().
  // JSON round-trip keeps this module Vue-free and matches what
  // snapshotsEqual already compares against.
  return JSON.parse(JSON.stringify(snapshot)) as SketchSnapshot
}

export function snapshotsEqual(a: SketchSnapshot, b: SketchSnapshot): boolean {
  // Graphs here stay under a few hundred nodes (docking ligands), so a
  // structural stringify is cheaper and simpler than a field-by-field diff.
  return JSON.stringify(a) === JSON.stringify(b)
}

export function atomById(snapshot: SketchSnapshot, id: number): SketchAtom | undefined {
  return snapshot.atoms.find((atom) => atom.id === id)
}

/** Unordered key: bonds are never directed for lookup purposes. */
export function bondKey(a1: number, a2: number): string {
  return a1 < a2 ? `${a1}:${a2}` : `${a2}:${a1}`
}

export function findBond(snapshot: SketchSnapshot, a1: number, a2: number): SketchBond | undefined {
  return snapshot.bonds.find(
    (bond) => (bond.a1 === a1 && bond.a2 === a2) || (bond.a1 === a2 && bond.a2 === a1),
  )
}

export function bondsOf(snapshot: SketchSnapshot, id: number): SketchBond[] {
  return snapshot.bonds.filter((bond) => bond.a1 === id || bond.a2 === id)
}

export function neighborsOf(snapshot: SketchSnapshot, id: number): number[] {
  return bondsOf(snapshot, id).map((bond) => (bond.a1 === id ? bond.a2 : bond.a1))
}

export function addAtom(
  snapshot: SketchSnapshot,
  symbol: string,
  x: number,
  y: number,
  charge = 0,
): SketchAtom {
  const atom: SketchAtom = { id: snapshot.nextId, symbol, x, y, charge, radical: 0 }
  snapshot.nextId += 1
  snapshot.atoms.push(atom)
  return atom
}

/** Returns null when the bond already exists or is degenerate. */
export function addBond(
  snapshot: SketchSnapshot,
  a1: number,
  a2: number,
  order: SketchBond['order'],
  stereo: SketchBond['stereo'],
): SketchBond | null {
  if (a1 === a2 || findBond(snapshot, a1, a2)) return null
  const bond: SketchBond = { a1, a2, order, stereo }
  snapshot.bonds.push(bond)
  return bond
}

export function removeAtom(snapshot: SketchSnapshot, id: number): void {
  const index = snapshot.atoms.findIndex((atom) => atom.id === id)
  if (index >= 0) snapshot.atoms.splice(index, 1)
  snapshot.bonds = snapshot.bonds.filter((bond) => bond.a1 !== id && bond.a2 !== id)
}

export function removeBond(snapshot: SketchSnapshot, a1: number, a2: number): boolean {
  const before = snapshot.bonds.length
  snapshot.bonds = snapshot.bonds.filter(
    (bond) => !((bond.a1 === a1 && bond.a2 === a2) || (bond.a1 === a2 && bond.a2 === a1)),
  )
  return snapshot.bonds.length < before
}

/** BFS over bonds; used by double-click "select connected component". */
export function connectedComponent(snapshot: SketchSnapshot, startId: number): number[] {
  if (!atomById(snapshot, startId)) return []
  const seen = new Set<number>([startId])
  const queue = [startId]
  while (queue.length > 0) {
    const id = queue.shift() as number
    for (const bond of bondsOf(snapshot, id)) {
      const next = bond.a1 === id ? bond.a2 : bond.a1
      if (!seen.has(next)) {
        seen.add(next)
        queue.push(next)
      }
    }
  }
  return [...seen]
}

/** Skeletal carbons hide their label: bonded, neutral, non-radical carbon. */
export function isSkeletonCarbon(snapshot: SketchSnapshot, id: number): boolean {
  const atom = atomById(snapshot, id)
  return (
    !!atom &&
    atom.symbol === 'C' &&
    atom.charge === 0 &&
    atom.radical === 0 &&
    bondsOf(snapshot, id).length > 0
  )
}
