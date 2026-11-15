import type { ReceptorSequence } from '@/types/api'

/** Toggle one residue key without mutating the caller's set. */
export function toggleResidueKey(selected: Set<string>, key: string): Set<string> {
  const next = new Set(selected)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  return next
}

/**
 * Add every polymer residue between two keys (inclusive) to the selection.
 *
 * The order is the sequence's display order, the same order `SequenceView`
 * renders; HET cells are skipped because they cannot be used as flexible or
 * selection residues here. Unknown endpoints leave the selection unchanged.
 */
export function addResidueRange(
  selected: Set<string>,
  sequence: ReceptorSequence | null,
  from: string,
  to: string,
): Set<string> {
  const flat: string[] = []
  for (const chain of sequence?.chains ?? []) {
    for (const residue of chain.residues) {
      if (!residue.het) flat.push(`${chain.id}:${residue.seqId}`)
    }
  }
  const start = flat.indexOf(from)
  const end = flat.indexOf(to)
  if (start < 0 || end < 0) return new Set(selected)

  const next = new Set(selected)
  for (let index = Math.min(start, end); index <= Math.max(start, end); index += 1) {
    const key = flat[index]
    if (key) next.add(key)
  }
  return next
}

/** Stable order for the request payload and for display. */
export function residueKeys(selected: Set<string>): string[] {
  return [...selected].sort()
}
