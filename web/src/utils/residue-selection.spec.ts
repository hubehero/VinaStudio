import { describe, expect, it } from 'vitest'

import type { ReceptorSequence } from '@/types/api'

import { addResidueRange, residueKeys, toggleResidueKey } from './residue-selection'

const sequence: ReceptorSequence = {
  chains: [
    {
      id: 'A',
      residues: [
        { seqId: 1, name: 'MET', het: false },
        { seqId: 2, name: 'ALA', het: false },
        { seqId: 3, name: 'GLY', het: false },
        { seqId: 4, name: 'HOH', het: true },
        { seqId: 5, name: 'SER', het: false },
      ],
    },
  ],
}

describe('residue selection', () => {
  it('toggles a key without mutating the input', () => {
    const original = new Set(['A:1'])
    const added = toggleResidueKey(original, 'A:2')
    expect([...original]).toEqual(['A:1'])
    expect([...added]).toEqual(['A:1', 'A:2'])

    const removed = toggleResidueKey(added, 'A:1')
    expect([...removed]).toEqual(['A:2'])
  })

  it('adds an inclusive range and skips HET residues', () => {
    const selected = addResidueRange(new Set(['A:1']), sequence, 'A:1', 'A:5')
    expect(residueKeys(selected)).toEqual(['A:1', 'A:2', 'A:3', 'A:5'])
  })

  it('leaves the selection unchanged for unknown endpoints', () => {
    const selected = addResidueRange(new Set(['A:1']), sequence, 'A:1', 'B:9')
    expect(residueKeys(selected)).toEqual(['A:1'])
  })

  it('returns a stable sorted payload', () => {
    expect(residueKeys(new Set(['A:5', 'A:1', 'A:3']))).toEqual(['A:1', 'A:3', 'A:5'])
  })
})
