import { describe, expect, it } from 'vitest'

import { buildMethodsText, type MethodsInput } from './methods-paragraph'

function input(preparation?: Record<string, unknown>): MethodsInput {
  return {
    params: {
      receptor_path: '/w/receptor.pdbqt',
      ligand_path: '/w/ligand.pdbqt',
      center: [1, 2, 3],
      size: [20, 20, 20],
      scoring: 'vina',
      exhaustiveness: 8,
      n_poses: 9,
      seed: 42,
      preparation,
    },
    receptorName: 'receptor.pdbqt',
    ligandName: 'ligand.pdbqt',
    versions: { vina: '1.2.7', meeko: '0.8.0', rdkit: '2026.9.1' },
    nPoses: 5,
    bestAffinity: -9.2,
    elapsedMs: 12_000,
    validation: null,
    rmsd: null,
    clusters: null,
  }
}

describe('Methods preparation summary', () => {
  it('records deletion, retention, histidine and altloc decisions', () => {
    const { body } = buildMethodsText(
      input({
        deletedWaters: 2,
        deletedHetero: 1,
        keptWaters: 1,
        keptHetero: 1,
        ignoredResidues: 3,
        histidineStates: ['A:246 HIP', 'A:295 HIE'],
        altlocPolicy: 'A',
        removedAltlocResidues: 2,
        incompleteResidues: 1,
        completenessPolicy: 'report-only',
      }),
      'en',
    )
    expect(body).toContain('removed 2 water molecule(s)')
    expect(body).toContain('kept 1 water(s)')
    expect(body).toContain('A:246 HIP')
    expect(body).toContain('altloc policy: A')
    expect(body).toContain('1 standard residue(s) have missing heavy atoms')
  })

  it('does not invent a preparation paragraph when none was recorded', () => {
    const { body } = buildMethodsText(input(), 'en')
    expect(body).not.toContain('Receptor preparation removed')
  })

  it('records how the search box was chosen', () => {
    const base = input()
    const en = buildMethodsText(
      { ...base, params: { ...base.params, box_source: 'ligand' } },
      'en',
    )
    expect(en.body).toContain('autoboxed from the ligand')

    const zh = buildMethodsText(
      { ...base, params: { ...base.params, box_source: 'pocket' } },
      'zh',
    )
    expect(zh.body).toContain('盒子来源：由候选位点确定')
  })

  it('renders the Chinese boundary sentence', () => {
    const { body } = buildMethodsText(
      input({
        deletedWaters: 0,
        deletedHetero: 0,
        keptWaters: 2,
        keptHetero: 0,
        ignoredResidues: 0,
        histidineStates: [],
        altlocPolicy: 'blank/default',
        removedAltlocResidues: 0,
        incompleteResidues: 1,
        completenessPolicy: 'report-only',
      }),
      'zh',
    )
    expect(body).toContain('保留 2 个水')
    expect(body).toContain('缺失重原子')
  })
})
