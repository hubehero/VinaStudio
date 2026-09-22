import type {
  Artifact,
  Detection,
  AutoboxFromResiduesOptions,
  AutoboxOptions,
  AutoboxResult,
  BatchDockingRequest,
  BatchJobCreated,
  BatchJobResult,
  BatchJobStatus,
  BoxMetrics,
  BoxSpec,
  Capabilities,
  CitationResponse,
  ConfigText,
  DockingDefaults,
  DockingJobCreated,
  InteractionData,
  VinaCiteResponse,
  DockingJobResult,
  DockingJobStatus,
  DockingJobSummary,
  DockingRequest,
  ExportPoseResponse,
  FileFilters,
  Health,
  LibraryEntry,
  LibraryFetchAllRequest,
  LibraryFetchAllResponse,
  LibraryFetchRequest,
  LibraryFetchResponse,
  LibrarySearchRequest,
  LibrarySearchResponse,
  LigandOptions,
  LigandPreparation,
  LigandPreview,
  OptimizeRequest,
  OptimizeResponse,
  RandomizeRequest,
  RandomizeResponse,
  ReceptorOptions,
  ReceptorPreparation,
  ReceptorPreview,
  SampleFile,
  SavedUpload,
  ScoreRequest,
  ScoreResponse,
  SelfCheck,
  SystemInfo,
  VinaInfoResponse,
  WorkspaceInfo,
  WriteMapsRequest,
  WriteMapsResponse,
} from '@/types/api'

/**
 * Relative URLs work in both modes: the bundled build is served by the same
 * FastAPI process, and the Vite dev server proxies `/api` to the desktop API.
 */
const JSON_HEADERS: HeadersInit = { 'Content-Type': 'application/json' }

export class ApiError extends Error {
  readonly status: number
  readonly detail: unknown

  constructor(message: string, status: number, detail: unknown = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

/** Turn whatever the API returned into something a user can read. */
function errorMessage(detail: unknown, response: Response): string {
  if (detail && typeof detail === 'object' && 'detail' in detail) {
    const body = (detail as { detail: unknown }).detail
    // FastAPI reports request validation as a list of {type, msg, loc} entries;
    // stringifying that yields "[object Object]" in place of the reason.
    if (Array.isArray(body)) {
      return body
        .map((entry) =>
          entry && typeof entry === 'object' && 'msg' in entry
            ? String((entry as { msg: unknown }).msg)
            : String(entry),
        )
        .join('; ')
    }
    return String(body)
  }
  return `${response.status} ${response.statusText}`
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response
  try {
    response = await fetch(path, { headers: JSON_HEADERS, ...init })
  } catch (cause) {
    throw new ApiError(`无法连接本地服务 / Cannot reach the local service`, 0, cause)
  }

  if (!response.ok) {
    let detail: unknown = null
    try {
      detail = await response.json()
    } catch {
      detail = await response.text().catch(() => null)
    }
    throw new ApiError(errorMessage(detail, response), response.status, detail)
  }

  if (response.status === 204) {
    return undefined as T
  }
  return (await response.json()) as T
}

export const api = {
  health: () => request<Health>('/api/system/health'),
  systemInfo: () => request<SystemInfo>('/api/system/info'),
  uploadLimit: () => request<{ bytes: number; megabytes: number }>('/api/system/upload-limit'),
  selfCheck: () => request<SelfCheck>('/api/system/selfcheck'),
  capabilities: () => request<Capabilities>('/api/system/capabilities'),
  citations: () => request<CitationResponse>('/api/system/citation'),

  // -- files ---------------------------------------------------------------
  fileFilters: () => request<FileFilters>('/api/files/filters'),
  samples: () => request<SampleFile[]>('/api/files/samples'),
  // `.pdb` and `.pdbqt` say nothing about what they hold; the server reads them.
  detect: (path: string) =>
    request<Detection>('/api/files/detect', {
      method: 'POST',
      body: JSON.stringify({ path }),
    }),
  // The viewport cannot draw PDBQT or mmCIF, so it draws the copy this writes.
  renderable: (path: string, kind: 'receptor' | 'ligand') =>
    request<Artifact[]>('/api/files/renderable', {
      method: 'POST',
      body: JSON.stringify({ path, kind }),
    }),
  upload: async (file: File): Promise<SavedUpload> => {
    const form = new FormData()
    form.append('file', file)
    // No JSON content type here: the browser must set the multipart boundary.
    const response = await fetch('/api/files/upload', { method: 'POST', body: form })
    if (!response.ok) {
      const detail = await response.text().catch(() => '')
      throw new ApiError(detail || `upload failed (${response.status})`, response.status)
    }
    return (await response.json()) as SavedUpload
  },

  // -- preparation ---------------------------------------------------------
  inspectLigand: (path: string) =>
    request<LigandPreview>('/api/ligand/inspect', {
      method: 'POST',
      body: JSON.stringify({ path }),
    }),
  prepareLigand: (path: string, options?: Partial<LigandOptions>) =>
    request<LigandPreparation>('/api/ligand/prepare', {
      method: 'POST',
      body: JSON.stringify({ path, options }),
    }),
  inspectReceptor: (path: string) =>
    request<ReceptorPreview>('/api/receptor/inspect', {
      method: 'POST',
      body: JSON.stringify({ path }),
    }),
  prepareReceptor: (path: string, options?: Partial<ReceptorOptions>) =>
    request<ReceptorPreparation>('/api/receptor/prepare', {
      method: 'POST',
      body: JSON.stringify({ path, options }),
    }),

  // -- search box ----------------------------------------------------------
  measureBox: (spec: BoxSpec) =>
    request<BoxMetrics>('/api/box/metrics', {
      method: 'POST',
      body: JSON.stringify(spec),
    }),
  autoboxFromLigand: (options: AutoboxOptions) =>
    request<AutoboxResult>('/api/box/from-ligand', {
      method: 'POST',
      body: JSON.stringify(options),
    }),
  autoboxFromResidues: (options: AutoboxFromResiduesOptions) =>
    request<AutoboxResult>('/api/box/from-residues', {
      method: 'POST',
      body: JSON.stringify(options),
    }),
  boxToConfig: (spec: BoxSpec) =>
    request<ConfigText>('/api/box/to-config', {
      method: 'POST',
      body: JSON.stringify(spec),
    }),
  boxFromConfig: (text: string) =>
    request<BoxMetrics>('/api/box/from-config', {
      method: 'POST',
      body: JSON.stringify({ text }),
    }),
  writeMaps: (options: WriteMapsRequest) =>
    request<WriteMapsResponse>('/api/box/write-maps', {
      method: 'POST',
      body: JSON.stringify(options),
    }),

  // -- docking --------------------------------------------------------------
  dockingDefaults: () => request<DockingDefaults>('/api/docking/defaults'),
  startDocking: (request_body: DockingRequest) =>
    request<DockingJobCreated>('/api/docking/start', {
      method: 'POST',
      body: JSON.stringify(request_body),
    }),
  batchDocking: (request_body: BatchDockingRequest) =>
    request<BatchJobCreated>('/api/docking/batch', {
      method: 'POST',
      body: JSON.stringify(request_body),
    }),
  batchStatus: (jobId: string) =>
    request<BatchJobStatus>(`/api/docking/batch/${jobId}`),
  batchResult: (jobId: string) =>
    request<BatchJobResult>(`/api/docking/batch/${jobId}/result`),
  dockingJobs: () => request<DockingJobSummary[]>('/api/docking/jobs'),
  dockingJobStatus: (jobId: string) =>
    request<DockingJobStatus>(`/api/docking/jobs/${jobId}`),
  dockingJobResult: (jobId: string) =>
    request<DockingJobResult>(`/api/docking/jobs/${jobId}/result`),
  cancelDocking: (jobId: string) =>
    request<{ status: string; jobId: string }>(`/api/docking/jobs/${jobId}/cancel`, {
      method: 'POST',
    }),
  scorePose: (body: ScoreRequest) =>
    request<ScoreResponse>('/api/docking/score', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  optimizePose: (body: OptimizeRequest) =>
    request<OptimizeResponse>('/api/docking/optimize', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  randomizePose: (body: RandomizeRequest) =>
    request<RandomizeResponse>('/api/docking/randomize', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  exportPose: (jobId: string, poseIndex: number) =>
    request<ExportPoseResponse>(`/api/docking/jobs/${jobId}/export-pose`, {
      method: 'POST',
      body: JSON.stringify({ poseIndex }),
    }),
  exportCsv: (jobId: string) =>
    request<{ csv: string; filename: string }>(`/api/docking/jobs/${jobId}/export-csv`),
  exportBatchCsv: (jobId: string) =>
    request<{ csv: string; filename: string }>(`/api/docking/batch/${jobId}/export-csv`),
  vinaInfo: () => request<VinaInfoResponse>('/api/docking/info'),
  vinaCite: (scoring: string = 'vina') =>
    request<VinaCiteResponse>(`/api/docking/cite?scoring=${encodeURIComponent(scoring)}`),

  // -- project --------------------------------------------------------------
  saveProject: (filename: string, project: Record<string, unknown>) =>
    request<{ path: string; filename: string; status: string }>('/api/project/save', {
      method: 'POST',
      body: JSON.stringify({ filename, project }),
    }),
  saveProjectAs: (path: string, project: Record<string, unknown>) =>
    request<{ path: string; filename: string; status: string }>('/api/project/save-as', {
      method: 'POST',
      body: JSON.stringify({ path, project }),
    }),
  loadProject: (path: string) =>
    request<{ path: string; project: Record<string, unknown> }>('/api/project/load', {
      method: 'POST',
      body: JSON.stringify({ path }),
    }),
  listProjects: () =>
    request<{ path: string; filename: string; name: string; createdAt: string; updatedAt: string; description: string }[]>('/api/project/list'),
  deleteProject: (filename: string) =>
    request<{ status: string; filename: string }>(`/api/project/${encodeURIComponent(filename)}`, {
      method: 'DELETE',
    }),

  // -- interactions ---------------------------------------------------------
  analyzeInteractions: (body: { receptorPath: string; ligandPath?: string; ligandPdbqtString?: string; distanceCutoff?: number }) =>
    request<{ interactions: InteractionData[]; count: number }>('/api/interactions/analyze', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  // -- molecule library (RCSB PDB) ------------------------------------------
  librarySearch: (body: LibrarySearchRequest) =>
    request<LibrarySearchResponse>('/api/library/search', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  libraryEntry: (pdbId: string) =>
    request<LibraryEntry>(`/api/library/entry/${encodeURIComponent(pdbId)}`),
  libraryFetch: (body: LibraryFetchRequest) =>
    request<LibraryFetchResponse>('/api/library/fetch', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  libraryFetchAll: (body: LibraryFetchAllRequest) =>
    request<LibraryFetchAllResponse>('/api/library/fetch-all', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  // -- workspace ------------------------------------------------------------
  getWorkspace: () =>
    request<WorkspaceInfo>('/api/workspace'),
  initWorkspace: (path: string, name?: string) =>
    request<WorkspaceInfo>('/api/workspace/init', {
      method: 'POST',
      body: JSON.stringify({ path, name }),
    }),
  setWorkspace: (path: string) =>
    request<WorkspaceInfo>('/api/workspace/set', {
      method: 'POST',
      body: JSON.stringify({ path }),
    }),
  migrateWorkspace: (targetPath: string) =>
    request<WorkspaceInfo>('/api/workspace/migrate', {
      method: 'POST',
      body: JSON.stringify({ targetPath }),
    }),
  renameWorkspace: (name: string) =>
    request<WorkspaceInfo>(`/api/workspace/name?name=${encodeURIComponent(name)}`, {
      method: 'PUT',
    }),
}

export type {
  AutoboxOptions,
  AutoboxResult,
  BoxMetrics,
  BoxSpec,
  Capabilities,
  CitationResponse,
  ConfigText,
  FileFilters,
  Health,
  LigandPreparation,
  LigandPreview,
  ReceptorPreparation,
  ReceptorPreview,
  SampleFile,
  SelfCheck,
  SystemInfo,
}
