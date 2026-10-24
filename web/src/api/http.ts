import type {
  AnalyzeInteractionsRequest,
  AnalyzeInteractionsResponse,
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
  ClusterResponse,
  ConfigText,
  DockingDefaults,
  DockingJobCreated,
  VinaCiteResponse,
  DockingJobResult,
  DockingJobStatus,
  DockingJobSummary,
  DockingRequest,
  EnsembleDockingRequest,
  ExportBundleRequest,
  ExportPoseResponse,
  FileFilters,
  Health,
  ImportBundleResponse,
  UpdateCheck,
  IfpGroupRequest,
  PocketsRequest,
  PocketsResult,
  SiteScreeningRequest,
  SiteScreeningResult,
  SiteScreeningStatus,
  IfpGroupResponse,
  IfpJobRequest,
  IfpJobResponse,
  LibraryDetail,
  LibraryEntry,
  LibraryFetchAllRequest,
  LibraryFetchAllResponse,
  LibraryFetchRequest,
  LibraryFetchResponse,
  LibraryImportResult,
  LibrarySearchRequest,
  LibrarySearchResponse,
  LibrarySummary,
  CompoundFetchRequest,
  CompoundFetchResponse,
  CompoundSearchPage,
  CompoundSearchRequest,
  CompoundSourceInfo,
  LigandOptions,
  LigandPreparation,
  LigandFromSmilesItem,
  LigandFromSmilesRequest,
  LigandPreview,
  OptimizeRequest,
  OptimizeResponse,
  PubChemFetchRequest,
  PubChemFetchResponse,
  RandomizeRequest,
  RandomizeResponse,
  RankingResponse,
  RankingSortBy,
  RmsdRequestBody,
  RmsdResponse,
  ReceptorOptions,
  ReceptorPreparation,
  ReceptorPreview,
  ResultRunDetail,
  ResultRunSummary,
  RunUpdateResponse,
  BulkUpdateResponse,
  SavedView,
  SavedViewCreate,
  TagCount,
  SampleFile,
  SavedUpload,
  ScreeningRunStatus,
  ScreeningRunSummary,
  ScreeningStartRequest,
  SketchAnalyzeRequest,
  SketchAnalyzeResponse,
  SketchCleanupResponse,
  SketchLayoutResponse,
  ScoreRequest,
  ScoreResponse,
  SelfCheck,
  SystemInfo,
  ValidatePosesRequest,
  ValidatePosesResponse,
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
  updateCheck: () => request<UpdateCheck>('/api/system/update-check'),

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
    // The custom header is required by the endpoint: it makes the request
    // non-simple, so a page the user is merely visiting cannot post a file to
    // this server without a preflight, which the server never grants.
    const response = await fetch('/api/files/upload', {
      method: 'POST',
      headers: { 'X-Requested-With': 'VinaStudio' },
      body: form,
    })
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
  // Paste SMILES → 3D SDF on disk → inspect + prepare in one round-trip.
  ligandFromSmiles: (body: LigandFromSmilesRequest) =>
    request<LigandFromSmilesItem[]>('/api/ligand/from-smiles', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  // Sketch chemical feedback: 200 with smiles=null while the drawing is
  // invalid — that is a verdict, not a transport failure.
  analyzeSketch: (body: SketchAnalyzeRequest) =>
    request<SketchAnalyzeResponse>('/api/chem/sketch/analyze', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  cleanupSketch: (body: SketchAnalyzeRequest) =>
    request<SketchCleanupResponse>('/api/chem/sketch/cleanup', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  layoutSketch: (smiles: string) =>
    request<SketchLayoutResponse>('/api/chem/sketch/layout', {
      method: 'POST',
      body: JSON.stringify({ smiles }),
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
  pockets: (options: PocketsRequest) =>
    request<PocketsResult>('/api/box/pockets', {
      method: 'POST',
      body: JSON.stringify(options),
    }),
  startSiteScreen: (options: SiteScreeningRequest) =>
    request<{ jobId: string; status: string }>('/api/sites/start', {
      method: 'POST',
      body: JSON.stringify(options),
    }),
  siteScreenStatus: (jobId: string) =>
    request<SiteScreeningStatus>(`/api/sites/${jobId}`),
  siteScreenResult: (jobId: string) =>
    request<SiteScreeningResult>(`/api/sites/${jobId}/result`),
  cancelSiteScreen: (jobId: string) =>
    request<{ status: string; jobId: string }>(`/api/sites/${jobId}/cancel`, {
      method: 'POST',
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
  startEnsembleDocking: (request_body: EnsembleDockingRequest) =>
    request<DockingJobCreated>('/api/docking/ensemble', {
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
  validatePoses: (jobId: string, body: ValidatePosesRequest = {}) =>
    request<ValidatePosesResponse>(`/api/docking/jobs/${jobId}/validate`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  jobRmsd: (jobId: string, body: RmsdRequestBody) =>
    request<RmsdResponse>(`/api/docking/jobs/${jobId}/rmsd`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  clusterPoses: (jobId: string, body: { cutoff?: number } = {}) =>
    request<ClusterResponse>(`/api/docking/jobs/${jobId}/cluster`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  exportCsv: (jobId: string, referencePath?: string) => {
    const query = referencePath ? `?referencePath=${encodeURIComponent(referencePath)}` : ''
    return request<{ csv: string; filename: string }>(
      `/api/docking/jobs/${jobId}/export-csv${query}`,
    )
  },
  exportBatchCsv: (jobId: string) =>
    request<{ csv: string; filename: string }>(`/api/docking/batch/${jobId}/export-csv`),
  exportBundle: (jobId: string, body: ExportBundleRequest) =>
    request<Artifact>(`/api/docking/jobs/${jobId}/export-bundle`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  importBundle: async (file: File): Promise<ImportBundleResponse> => {
    const form = new FormData()
    form.append('file', file)
    // Same non-simple-request guard as /api/files/upload: the endpoint
    // accepts bytes, never a filesystem path from the page.
    const response = await fetch('/api/docking/import-bundle', {
      method: 'POST',
      headers: { 'X-Requested-With': 'VinaStudio' },
      body: form,
    })
    if (!response.ok) {
      const detail = await response.text().catch(() => '')
      throw new ApiError(detail || `import failed (${response.status})`, response.status)
    }
    return (await response.json()) as ImportBundleResponse
  },
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
    request<{ path: string; project: Record<string, unknown>; warnings: string[] }>(
      '/api/project/load',
      {
        method: 'POST',
        body: JSON.stringify({ path }),
      },
    ),
  listProjects: () =>
    request<{ path: string; filename: string; name: string; createdAt: string; updatedAt: string; description: string }[]>('/api/project/list'),
  deleteProject: (filename: string) =>
    request<{ status: string; filename: string }>(`/api/project/${encodeURIComponent(filename)}`, {
      method: 'DELETE',
    }),

  // -- interactions ---------------------------------------------------------
  analyzeInteractions: (body: AnalyzeInteractionsRequest) =>
    request<AnalyzeInteractionsResponse>('/api/interactions/analyze', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  // -- molecule library (RCSB PDB / PubChem) --------------------------------
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
  pubchemFetch: (body: PubChemFetchRequest) =>
    request<PubChemFetchResponse>('/api/library/pubchem/fetch', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  // -- compound providers (PubChem / ChEMBL) --------------------------------
  compoundSources: () => request<CompoundSourceInfo[]>('/api/library/sources'),
  compoundSearch: (body: CompoundSearchRequest) =>
    request<CompoundSearchPage>('/api/library/compounds/search', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  compoundFetch: (body: CompoundFetchRequest) =>
    request<CompoundFetchResponse>('/api/library/compounds/fetch', {
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

  // -- molecule manifest (persistent storage) ---------------------------------
  listMolecules: () =>
    request<import('@/types/molecule').MoleculeManifest>('/api/molecules'),
  saveMolecules: (manifest: import('@/types/molecule').MoleculeManifest) =>
    request<{ status: string; count: number }>('/api/molecules/save', {
      method: 'POST',
      body: JSON.stringify(manifest),
    }),
  deleteMolecule: (id: string) =>
    request<{ status: string; count: number }>(`/api/molecules/${encodeURIComponent(id)}`, {
      method: 'DELETE',
    }),
  clearMolecules: () =>
    request<{ status: string; count: number }>('/api/molecules/clear', {
      method: 'POST',
    }),
  verifyMolecules: (ids: string[]) =>
    request<{ existing: string[]; missing: string[]; mtimes: Record<string, number> }>('/api/molecules/verify', {
      method: 'POST',
      body: JSON.stringify({ ids }),
    }),

  // -- results index (cross-project search) ---------------------------------
  resultsSearch: (
    q: string,
    options?: { limit?: number; offset?: number; favorites?: boolean; tags?: string[] },
  ) => {
    const params = new URLSearchParams({ q })
    if (options?.limit != null) params.set('limit', String(options.limit))
    if (options?.offset != null) params.set('offset', String(options.offset))
    if (options?.favorites) params.set('favorites', 'true')
    if (options?.tags && options.tags.length > 0) params.set('tags', options.tags.join(','))
    return request<ResultRunSummary[]>(`/api/results/search?${params.toString()}`)
  },
  resultsCompare: (runIds: string[]) =>
    request<ResultRunDetail[]>(
      `/api/results/compare?runIds=${encodeURIComponent(runIds.join(','))}`,
    ),
  resultsTags: () => request<TagCount[]>('/api/results/tags'),
  resultsUpdateRun: (jobId: string, body: { favorite?: boolean; tags?: string[] }) =>
    request<RunUpdateResponse>(`/api/results/runs/${encodeURIComponent(jobId)}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  resultsBulkUpdate: (body: {
    runIds: string[]
    favorite?: boolean
    addTags?: string[]
    removeTags?: string[]
  }) =>
    request<BulkUpdateResponse>('/api/results/runs/bulk', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  resultsViews: () => request<SavedView[]>('/api/results/views'),
  resultsSaveView: (body: SavedViewCreate) =>
    request<SavedView>('/api/results/views', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  resultsDeleteView: (id: number) =>
    request<void>(`/api/results/views/${id}`, { method: 'DELETE' }),

  // -- virtual screening (TASK-13) ------------------------------------------
  screeningLibraries: () => request<LibrarySummary[]>('/api/screening/libraries'),
  screeningImport: async (form: FormData): Promise<LibraryImportResult> => {
    // Multipart: the browser must set the boundary, so JSON_HEADERS is wrong.
    const response = await fetch('/api/screening/libraries/import', {
      method: 'POST',
      body: form,
    })
    if (!response.ok) {
      let detail: unknown = null
      try {
        detail = await response.json()
      } catch {
        detail = await response.text().catch(() => null)
      }
      throw new ApiError(errorMessage(detail, response), response.status, detail)
    }
    return (await response.json()) as LibraryImportResult
  },
  screeningLibrary: (name: string) =>
    request<LibraryDetail>(`/api/screening/libraries/${encodeURIComponent(name)}`),
  screeningRuns: () => request<ScreeningRunSummary[]>('/api/screening/runs'),
  screeningRun: (id: string) =>
    request<ScreeningRunStatus>(`/api/screening/runs/${encodeURIComponent(id)}`),
  screeningStart: (body: ScreeningStartRequest) =>
    request<{ jobId: string }>('/api/screening/runs', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  screeningResume: (id: string) =>
    request<ScreeningRunStatus>(`/api/screening/runs/${encodeURIComponent(id)}/resume`, {
      method: 'POST',
    }),
  screeningCancel: (id: string) =>
    request<void>(`/api/screening/runs/${encodeURIComponent(id)}/cancel`, {
      method: 'POST',
    }),
  screeningRanking: (id: string, sortBy: RankingSortBy, top: number) =>
    request<RankingResponse>(
      `/api/screening/runs/${encodeURIComponent(id)}/ranking?sortBy=${sortBy}&top=${top}`,
    ),
  screeningExportRanking: (id: string, sortBy: RankingSortBy, top: number) =>
    request<{ csv: string; filename: string }>(
      `/api/screening/runs/${encodeURIComponent(id)}/ranking/export?sortBy=${sortBy}&top=${top}`,
    ),

  // -- interaction fingerprints (TASK-16) -------------------------------------
  jobIfp: (jobId: string, body: IfpJobRequest) =>
    request<IfpJobResponse>(`/api/docking/jobs/${encodeURIComponent(jobId)}/ifp`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  ifpCluster: (body: IfpGroupRequest) =>
    request<IfpGroupResponse>('/api/results/ifp-cluster', {
      method: 'POST',
      body: JSON.stringify(body),
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
  LigandFromSmilesItem,
  LigandPreview,
  ReceptorPreparation,
  ReceptorPreview,
  SampleFile,
  SelfCheck,
  SystemInfo,
}
