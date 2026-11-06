import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  search: vi.fn(),
  adopt: vi.fn(),
}))

vi.mock('@/api/http', () => ({
  api: { catalogSearch: mocks.search },
}))

vi.mock('@/stores/molecules', () => ({
  useMoleculeStore: () => ({ adoptCatalogMolecule: mocks.adopt }),
}))

import { useCatalogStore } from './catalog'

function catalogItem(id: string, kind: string, prepared = true) {
  return {
    id,
    name: id,
    prepStatus: prepared ? 'prepared' : 'unprepared',
    files: [{ kind, path: `/tmp/${id}.pdbqt` }],
  }
}

describe('catalog pipeline bridge', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    mocks.search.mockReset()
    mocks.adopt.mockReset()
  })

  it('adopts only prepared molecules with a docking artifact', async () => {
    mocks.search.mockResolvedValue({
      items: [catalogItem('receptor', 'pdbqt'), catalogItem('ligand', 'sdf', false)],
      total: 2,
      limit: 200,
      offset: 0,
      facets: { source: [], status: [], prep: [], tags: [] },
    })

    await useCatalogStore().adoptPreparedForPipeline()

    expect(mocks.adopt).toHaveBeenCalledTimes(1)
    expect(mocks.adopt.mock.calls[0]?.[0]).toMatchObject({ id: 'receptor' })
  })

  it('pages through every prepared molecule', async () => {
    mocks.search
      .mockResolvedValueOnce({
        items: [catalogItem('a', 'pdbqt')],
        total: 2,
        limit: 200,
        offset: 0,
        facets: { source: [], status: [], prep: [], tags: [] },
      })
      .mockResolvedValueOnce({
        items: [catalogItem('b', 'pdbqt')],
        total: 2,
        limit: 200,
        offset: 1,
        facets: { source: [], status: [], prep: [], tags: [] },
      })

    await useCatalogStore().adoptPreparedForPipeline()

    expect(mocks.search).toHaveBeenCalledTimes(2)
    expect(mocks.adopt).toHaveBeenCalledTimes(2)
  })
})
