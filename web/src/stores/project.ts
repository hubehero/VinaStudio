import { defineStore } from 'pinia'
import { ref } from 'vue'

import { api } from '@/api/http'
import { useBoxStore } from '@/stores/box'
import { useMoleculeStore } from '@/stores/molecules'
import type { ProjectFile, ProjectListEntry } from '@/types/api'

export const useProjectStore = defineStore('project', () => {
  const currentProject = ref<ProjectFile | null>(null)
  const currentPath = ref<string | null>(null)
  const projectName = ref('untitled')
  const isDirty = ref(false)
  const savedProjects = ref<ProjectListEntry[]>([])

  function newProject(): void {
    currentProject.value = null
    currentPath.value = null
    projectName.value = 'untitled'
    isDirty.value = false
  }

  function markDirty(): void {
    isDirty.value = true
  }

  async function saveProject(filename?: string): Promise<string | null> {
    const name = filename ?? projectName.value
    const project = buildProjectData()
    try {
      const result = await api.saveProject(name, project as unknown as Record<string, unknown>)
      currentPath.value = result.path
      projectName.value = name
      isDirty.value = false
      return result.path
    } catch {
      return null
    }
  }

  async function saveProjectAs(path: string): Promise<string | null> {
    const project = buildProjectData()
    try {
      const result = await api.saveProjectAs(path, project as unknown as Record<string, unknown>)
      currentPath.value = result.path
      projectName.value = result.filename.replace('.vinaproj', '')
      isDirty.value = false
      return result.path
    } catch {
      return null
    }
  }

  async function loadProject(path: string): Promise<boolean> {
    try {
      const result = await api.loadProject(path)
      currentProject.value = result.project as unknown as ProjectFile
      currentPath.value = result.path
      projectName.value = currentProject.value.name || 'untitled'
      isDirty.value = false
      restoreFromProject(currentProject.value)
      return true
    } catch {
      return false
    }
  }

  async function refreshProjectList(): Promise<void> {
    try {
      savedProjects.value = await api.listProjects()
    } catch {
      savedProjects.value = []
    }
  }

  async function deleteProject(filename: string): Promise<boolean> {
    try {
      await api.deleteProject(filename)
      await refreshProjectList()
      return true
    } catch {
      return false
    }
  }

  /**
   * Read the live viewer state and write it into a project object.
   *
   * This replaces the old self-copying ``buildProjectData``: the receptor and
   * ligand paths now come from the pipeline picks (the files the user chose
   * for docking), the box from the box store, so saving captures the actual
   * working state instead of the last loaded skeleton.
   */
  function buildProjectData(): ProjectFile {
    const molecules = useMoleculeStore()
    const box = useBoxStore()

    const receptor = molecules.pipelineReceptor
    const ligand = molecules.pipelineLigand

    return {
      formatVersion: '1.0',
      createdAt: currentProject.value?.createdAt ?? new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      name: projectName.value,
      description: currentProject.value?.description ?? '',
      receptor: receptor
        ? { path: molecules.receptorPdbqtPath ?? receptor.path, flexPath: molecules.flexReceptorPath }
        : null,
      ligands: ligand
        ? [{ label: ligand.name, path: molecules.ligandPdbqtPath ?? ligand.path, pdbqtString: null }]
        : [],
      box: {
        center: [...box.center],
        size: [...box.size],
      },
      docking: currentProject.value?.docking ?? {
        scoring: 'vina',
        exhaustiveness: 8,
        nPoses: 20,
        energyRange: 3.0,
        minRmsd: 1.0,
        cpu: 0,
        seed: 0,
        noRefine: false,
      },
      lastJobId: currentProject.value?.lastJobId ?? null,
      results: currentProject.value?.results ?? [],
    }
  }

  /**
   * Push project state into the viewer stores so the interface reflects the
   * loaded project rather than remaining unchanged.
   *
   * Molecule paths are added best-effort: if the file is accessible the user
   * can inspect and prepare it from the molecule manager; if not the path is
   * preserved in the project for later.  The box is always restored because it
   * is pure data with no filesystem dependency.
   */
  function restoreFromProject(project: ProjectFile): void {
    const box = useBoxStore()
    const molecules = useMoleculeStore()

    // Restore box — pure data, always succeeds.
    if (project.box) {
      box.setCenter(project.box.center as [number, number, number])
      box.setSize(project.box.size as [number, number, number])
    }

    // Restore receptor — add from path and set as pipeline pick.
    if (project.receptor?.path) {
      const existing = molecules.findByPath(project.receptor.path)
      if (existing) {
        molecules.setPipelineReceptor(existing.id)
      } else {
        const item = molecules.addFromPath(project.receptor.path)
        molecules.assignType(item.id, 'receptor')
        molecules.setPipelineReceptor(item.id)
      }
    }

    // Restore ligand — first ligand entry.
    const ligand = project.ligands?.[0]
    if (ligand?.path) {
      const existing = molecules.findByPath(ligand.path)
      if (existing) {
        molecules.setPipelineLigand(existing.id)
      } else {
        const item = molecules.addFromPath(ligand.path, ligand.label)
        molecules.assignType(item.id, 'ligand')
        molecules.setPipelineLigand(item.id)
      }
    }
  }

  return {
    currentProject,
    currentPath,
    projectName,
    isDirty,
    savedProjects,
    newProject,
    markDirty,
    saveProject,
    saveProjectAs,
    loadProject,
    refreshProjectList,
    deleteProject,
  }
})
