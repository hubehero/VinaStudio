import { ElMessage } from 'element-plus'
import { defineStore } from 'pinia'
import { ref } from 'vue'

import { api } from '@/api/http'
import { i18n } from '@/i18n'
import { useBoxStore } from '@/stores/box'
import { useMoleculeStore } from '@/stores/molecules'
import type { ProjectFile, ProjectListEntry } from '@/types/api'

export const useProjectStore = defineStore('project', () => {
  const currentProject = ref<ProjectFile | null>(null)
  const currentPath = ref<string | null>(null)
  const projectName = ref('untitled')
  const isDirty = ref(false)
  const savedProjects = ref<ProjectListEntry[]>([])
  /** Result references whose artifacts no longer exist (load, TASK-07). */
  const loadWarnings = ref<string[]>([])

  function newProject(): void {
    currentProject.value = null
    currentPath.value = null
    projectName.value = 'untitled'
    isDirty.value = false
  }

  function markDirty(): void {
    isDirty.value = true
  }

  /**
   * Save to the current project file, or create one in the workspace.
   *
   * Ctrl+S must overwrite the file the user opened; the old path called
   * `/save`, whose uniqueness loop turned every Ctrl+S into a new `_1` copy.
   * A loaded project therefore goes through save-as at its existing path,
   * while a new project still gets a workspace filename.
   */
  async function saveProject(filename?: string): Promise<string | null> {
    const name = normaliseName(filename)
    if (currentPath.value) {
      return saveProjectToPath(currentPath.value, name)
    }
    const project = buildProjectData(name)
    try {
      const result = await api.saveProject(name, project as unknown as Record<string, unknown>)
      rememberSaved(result.path, name, project)
      return result.path
    } catch {
      return null
    }
  }

  /** Save As always writes exactly the path chosen in the native dialog. */
  async function saveProjectAs(path: string, filename?: string): Promise<string | null> {
    const name = normaliseName(filename || path.replace(/\.vinaproj$/i, '').split(/[\\/]/).pop())
    return saveProjectToPath(path, name)
  }

  async function saveProjectToPath(path: string, name: string): Promise<string | null> {
    const project = buildProjectData(name)
    try {
      const result = await api.saveProjectAs(path, project as unknown as Record<string, unknown>)
      rememberSaved(result.path, name, project)
      return result.path
    } catch {
      return null
    }
  }

  function normaliseName(value?: string): string {
    return (value ?? projectName.value).trim() || 'untitled'
  }

  /** Serialise the live viewer state for the browser Save As download. */
  function serializeProject(name?: string): ProjectFile {
    return buildProjectData(normaliseName(name))
  }

  function rememberSaved(path: string, name: string, project: ProjectFile): void {
    currentPath.value = path
    projectName.value = name
    // Keep a live project object after the first save. Result references and
    // createdAt are written from it; leaving it null made both reset.
    currentProject.value = {
      ...project,
      name,
      updatedAt: new Date().toISOString(),
    }
    isDirty.value = false
  }

  async function loadProject(path: string): Promise<boolean> {
    try {
      const result = await api.loadProject(path)
      currentProject.value = result.project as unknown as ProjectFile
      currentPath.value = result.path
      projectName.value = currentProject.value.name || 'untitled'
      isDirty.value = false
      loadWarnings.value = result.warnings ?? []
      if (loadWarnings.value.length > 0) {
        // The project still loads — a stale reference is a notice, not an error.
        ElMessage.warning(
          i18n.global.t('project.resultsMissing', { count: loadWarnings.value.length }),
        )
      }
      await restoreFromProject(currentProject.value)
      return true
    } catch {
      return false
    }
  }

  /**
   * Remember a finished job as a project result reference (format 1.1).
   *
   * Dedup by jobId: polling after completion re-runs this path. Without an
   * open project there is nothing to write the reference into, so it is a
   * silent no-op rather than an error.
   */
  function recordResult(jobId: string, label: string): void {
    const project = currentProject.value
    if (!project) return
    const results = project.results ?? []
    if (!results.some((r) => r.jobId === jobId)) {
      results.push({ jobId, label })
      project.results = results
      isDirty.value = true
    }
    if (project.lastJobId !== jobId) {
      project.lastJobId = jobId
      isDirty.value = true
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
  function buildProjectData(name = projectName.value): ProjectFile {
    const molecules = useMoleculeStore()
    const box = useBoxStore()

    const receptor = molecules.pipelineReceptor
    const ligand = molecules.pipelineLigand

    return {
      formatVersion: '1.1',
      createdAt: currentProject.value?.createdAt ?? new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      name,
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
  async function restoreFromProject(project: ProjectFile): Promise<void> {
    const box = useBoxStore()
    const molecules = useMoleculeStore()

    // Restore box — pure data, always succeeds.
    if (project.box) {
      box.setCenter(project.box.center as [number, number, number])
      box.setSize(project.box.size as [number, number, number])
    }

    // Restore receptor — reuse the prepared molecule by source or artifact path.
    if (project.receptor?.path) {
      const existing = molecules.findByAnyPath(project.receptor.path)
      if (existing) {
        molecules.setPipelineReceptor(existing.id)
      } else {
        const item = molecules.addFromPath(project.receptor.path)
        molecules.assignType(item.id, 'receptor')
        // A fresh session has no artifacts in memory; inspect the stored PDBQT
        // so it becomes usable (already-PDBQT is adopted as-is).
        await molecules.inspectMolecule(item.id)
        molecules.setPipelineReceptor(item.id)
      }
    }

    // Restore ligand — first ligand entry.
    const ligand = project.ligands?.[0]
    if (ligand?.path) {
      const existing = molecules.findByAnyPath(ligand.path)
      if (existing) {
        molecules.setPipelineLigand(existing.id)
      } else {
        // The project stores the prepared PDBQT path but the label may still be
        // the source SDF name. Showing "name.sdf" next to a PDBQT path made the
        // list claim SDF while the viewer read PDBQT.
        const basename = ligand.path.split(/[\\/]/).pop() ?? ligand.label
        const labelExtension = ligand.label.includes('.')
          ? ligand.label.slice(ligand.label.lastIndexOf('.')).toLowerCase()
          : ''
        const pathExtension = basename.slice(basename.lastIndexOf('.')).toLowerCase()
        const name = labelExtension && labelExtension === pathExtension ? ligand.label : basename
        const item = molecules.addFromPath(ligand.path, name)
        molecules.assignType(item.id, 'ligand')
        await molecules.inspectMolecule(item.id)
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
    loadWarnings,
    newProject,
    markDirty,
    saveProject,
    saveProjectAs,
    serializeProject,
    loadProject,
    recordResult,
    refreshProjectList,
    deleteProject,
  }
})
