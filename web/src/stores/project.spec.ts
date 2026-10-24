import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { api } from '@/api/http'
import { useProjectStore } from './project'

vi.mock('@/api/http', () => ({
  api: {
    saveProject: vi.fn(),
    saveProjectAs: vi.fn(),
  },
}))

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
})

describe('project persistence', () => {
  it('saves a new project into the workspace and keeps a live project object', async () => {
    vi.mocked(api.saveProject).mockResolvedValue({
      path: '/workspace/projects/first.vinaproj',
      filename: 'first.vinaproj',
      status: 'saved',
    })
    const project = useProjectStore()
    project.projectName = 'first'

    const path = await project.saveProject()

    expect(path).toBe('/workspace/projects/first.vinaproj')
    expect(api.saveProject).toHaveBeenCalledWith(
      'first',
      expect.objectContaining({ name: 'first' }),
    )
    expect(project.currentPath).toBe('/workspace/projects/first.vinaproj')
    expect(project.currentProject?.name).toBe('first')
    expect(project.isDirty).toBe(false)
  })

  it('overwrites the current path instead of creating a _1 copy', async () => {
    vi.mocked(api.saveProject).mockResolvedValue({
      path: '/workspace/projects/first.vinaproj',
      filename: 'first.vinaproj',
      status: 'saved',
    })
    vi.mocked(api.saveProjectAs).mockResolvedValue({
      path: '/workspace/projects/first.vinaproj',
      filename: 'first.vinaproj',
      status: 'saved',
    })
    const project = useProjectStore()
    project.projectName = 'first'
    await project.saveProject()

    await project.saveProject('renamed')

    expect(api.saveProject).toHaveBeenCalledTimes(1)
    expect(api.saveProjectAs).toHaveBeenCalledWith(
      '/workspace/projects/first.vinaproj',
      expect.objectContaining({ name: 'renamed' }),
    )
    expect(project.projectName).toBe('renamed')
  })

  it('uses the selected filename as the display name for Save As', async () => {
    vi.mocked(api.saveProjectAs).mockResolvedValue({
      path: '/tmp/my-project.vinaproj',
      filename: 'my-project.vinaproj',
      status: 'saved',
    })
    const project = useProjectStore()

    await project.saveProjectAs('/tmp/my-project.vinaproj')

    expect(api.saveProjectAs).toHaveBeenCalledWith(
      '/tmp/my-project.vinaproj',
      expect.objectContaining({ name: 'my-project' }),
    )
    expect(project.currentPath).toBe('/tmp/my-project.vinaproj')
    expect(project.projectName).toBe('my-project')
  })
})
