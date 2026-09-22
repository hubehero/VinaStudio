/** Shapes mirroring the FastAPI response models. Keep in sync with `vinastudio/schemas`. */

export type ScoringFunction = 'vina' | 'vinardo' | 'ad4'

export interface AppInfo {
  name: string
  version: string
}

export interface RuntimeInfo {
  python: string
  implementation: string
  platform: string
  platformRelease: string
  machine: string
}

export interface SystemInfo {
  app: AppInfo
  runtime: RuntimeInfo
  home: string
  packages: Record<string, string | null>
}

export interface PackageCheck {
  distribution: string
  module: string
  version: string | null
  importable: boolean
  error: string | null
  importMs: number
}

export interface SelfCheck {
  ok: boolean
  failed: string[]
  checks: PackageCheck[]
  dockingAvailable: boolean
}

export interface ScoringFunctionSpec {
  name: ScoringFunction
  label: string
  weights: number
  nativeMaps: boolean
  notes: string
}

export interface Capabilities {
  scoringFunctions: ScoringFunctionSpec[]
  ligandInputFormats: string[]
  receptorInputFormats: string[]
  outputFormats: string[]
  viewer: { engine: string; formats: string[]; note: string }
  languages: string[]
}

export interface CitationEntry {
  title: string
  authors: string
  venue: string
  year: number
  doi: string
}

export interface CitationResponse {
  entries: CitationEntry[]
}

export interface Health {
  status: string
  app: string
  version: string
  uptimeSeconds: number
  eventClients: number
}

// --------------------------------------------------------------------------
// preparation
// --------------------------------------------------------------------------

export type ArtifactKind = 'pdbqt' | 'pdb' | 'sdf' | 'json' | 'log' | 'text'

export interface Artifact {
  name: string
  path: string
  url: string
  bytes: number
  kind: ArtifactKind
}

export interface RunInfo {
  runId: string
  directory: string
}

export interface FileFilters {
  ligand: string
  receptor: string
  ligandSuffixes: string[]
  receptorSuffixes: string[]
}

export interface FileInspection {
  path: string
  exists: boolean
  suffix: string
  bytes: number
  format: string | null
  looksLikeLigand: boolean
  looksLikeReceptor: boolean
}

export interface SavedUpload {
  path: string
  name: string
  bytes: number
  suffix: string
}

export interface SampleFile {
  name: string
  path: string
  description: string
  bytes: number
}

export interface LigandPreview {
  source: string
  inputFormat: string
  preparable: boolean
  atoms: number
  hydrogens: number
  has3dCoordinates: boolean
  rotatableBonds: number
  molecularFormula: string | null
  molecularWeight: number | null
  smiles: string | null
  records: number
  notes: string[]
}

export interface LigandOptions {
  optimiseGeometry: boolean
  embedSeed: number
  rigidMacrocycles: boolean
  flexibleAmides: boolean
  hydrate: boolean
  doubleBondPenalty: number
}

export interface LigandReport {
  source: string
  inputFormat: string
  inputAtoms: number
  hydrogensAdded: number
  conformerGenerated: boolean
  geometryOptimised: boolean
  outputAtoms: number
  outputPolarHydrogens: number
  nonpolarHydrogensRemoved: number
  rotatableBonds: number
  totalCharge: number
  atomTypes: Record<string, number>
  smiles: string | null
  warnings: string[]
}

export interface LigandPreparation {
  run: RunInfo
  report: LigandReport
  artifacts: Artifact[]
  pdbqt: string
}

export interface ReceptorPreview {
  source: string
  inputFormat: string
  preparable: boolean
  atoms: number
  residues: number
  chains: number
  waters: string[]
  hetero: string[]
  residueNames: string[]
  notes: string[]
}

export interface ReceptorOptions {
  deleteWaters: boolean
  deleteHetero: boolean
  flexibleResidues: string[]
  allowBadResidues: boolean
  normaliseAtomOrder: boolean
}

export interface ReceptorReport {
  source: string
  inputFormat: string
  inputAtoms: number
  inputResidues: number
  deletedWaters: string[]
  deletedHetero: string[]
  normalisedAtomOrder: boolean
  validResidues: number
  ignoredResidues: string[]
  flexibleResidues: string[]
  residueList: string[]
  outputAtoms: number
  atomTypes: Record<string, number>
  includeHydrogens: boolean
  warnings: string[]
}

export interface ReceptorPreparation {
  run: RunInfo
  report: ReceptorReport
  artifacts: Artifact[]
  hasFlexibleSidechains: boolean
}

/** Error payload produced by the domain-error handler. */
export interface DomainErrorBody {
  detail: string
  kind: string
  residues?: string[]
}

// --------------------------------------------------------------------------
// search box
// --------------------------------------------------------------------------

export interface BoxSpec {
  center: [number, number, number]
  size: [number, number, number]
  spacing: number
  forceEvenVoxels: boolean
}

export interface BoxMetrics extends BoxSpec {
  voxels: number[]
  gridPoints: number[]
  volume: number
  canWriteMaps: boolean
  limits: number[][]
  warnings: string[]
}

export interface AutoboxOptions {
  path: string
  extend: number
  spacing: number
  forceEvenVoxels: boolean
  includeHydrogens?: boolean
}

export interface AutoboxFromResiduesOptions extends AutoboxOptions {
  residues: string[]
}

export interface AutoboxResult {
  box: BoxMetrics
  points: number
  source: string
}

export interface ConfigText {
  text: string
}

export interface WriteMapsRequest {
  receptorPath: string
  center: [number, number, number]
  size: [number, number, number]
  spacing: number
  forceEvenVoxels: boolean
  outputPrefix: string
}

export interface WriteMapsResponse {
  maps: string[]
  gpf: string | null
}

// --------------------------------------------------------------------------
// docking
// --------------------------------------------------------------------------

export type DockingStatus = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'

export interface DockingRequest {
  receptorPath: string
  flexReceptorPath: string | null
  ligandPath: string | null
  ligandPdbqtString: string | null
  center: [number, number, number]
  size: [number, number, number]
  scoring: ScoringFunction
  exhaustiveness: number
  nPoses: number
  energyRange: number
  minRmsd: number
  maxEvals: number
  cpu: number
  seed: number
  noRefine: boolean
  verbosity: number
  spacing: number
  forceEvenVoxels: boolean
  weights: number[] | null
  mapPaths: string[] | null
}

export interface DockingDefaults {
  scoring: ScoringFunction
  exhaustiveness: number
  nPoses: number
  energyRange: number
  minRmsd: number
  maxEvals: number
  cpu: number
  seed: number
  noRefine: boolean
  verbosity: number
  weightCounts: Record<string, number>
}

export interface DockingJobCreated {
  jobId: string
  status: 'queued'
}

export interface DockingJobStatus {
  jobId: string
  status: DockingStatus
  progress: number
  stage: string | null
  log: string[]
  error: string | null
  elapsedMs: number | null
}

export interface DockingJobSummary {
  jobId: string
  status: DockingStatus
  progress: number
  stage: string | null
  scoring: ScoringFunction
  elapsedMs: number | null
}

export interface PoseInfo {
  index: number
  affinity: number
  rmsdLower: number
  rmsdUpper: number
}

export interface DockingJobResult {
  jobId: string
  status: 'completed'
  poses: PoseInfo[]
  bestAffinity: number
  posesPdbqt: string
  posesSdf: string
  nPoses: number
  scoring: ScoringFunction
  elapsedMs: number
  artifacts: Artifact[]
}

/** WebSocket event from a docking job. */
export interface DockingEvent {
  type: string
  jobId: string
  [key: string]: unknown
}

// --------------------------------------------------------------------------
// score / optimize / randomize
// --------------------------------------------------------------------------

export interface ScoreRequest {
  receptorPath: string
  flexReceptorPath: string | null
  ligandPath: string | null
  ligandPdbqtString: string | null
  center: [number, number, number]
  size: [number, number, number]
  scoring: ScoringFunction
  spacing: number
  forceEvenVoxels: boolean
  unboundEnergy: number | null
}

export interface ScoreResponse {
  total: number
  inter: number
  intra: number
  torsions: number
  intra_best: number
}

export interface OptimizeRequest {
  receptorPath: string
  flexReceptorPath: string | null
  ligandPath: string | null
  ligandPdbqtString: string | null
  center: [number, number, number]
  size: [number, number, number]
  scoring: ScoringFunction
  spacing: number
  forceEvenVoxels: boolean
  maxSteps: number
}

export interface OptimizeResponse {
  energy: number
  ligandPdbqt: string
}

export interface RandomizeRequest {
  receptorPath: string
  flexReceptorPath: string | null
  ligandPath: string | null
  ligandPdbqtString: string | null
  center: [number, number, number]
  size: [number, number, number]
  scoring: ScoringFunction
  spacing: number
  forceEvenVoxels: boolean
  maxSteps: number
  seed: number
}

export interface RandomizeResponse {
  ligandPdbqt: string
}

export interface ExportPoseRequest {
  poseIndex: number
}

export interface ExportPoseResponse {
  poseIndex: number
  affinity: number
  pdbqt: string
  sdf: string
}

export interface VinaInfoResponse {
  version: string
  supportedScoringFunctions: string[]
  cpuCount: number
  maxCPUs: number
}

export interface VinaCiteResponse {
  function: string
  citation: string
}

export interface BatchLigandItem {
  ligandPath: string | null
  ligandPdbqtString: string | null
  label: string
}

export interface BatchDockingRequest {
  receptorPath: string
  flexReceptorPath: string | null
  center: [number, number, number]
  size: [number, number, number]
  ligands: BatchLigandItem[]
  scoring: ScoringFunction
  exhaustiveness: number
  nPoses: number
  energyRange: number
  minRmsd: number
  cpu: number
  seed: number
  noRefine: boolean
}

export interface BatchLigandResult {
  ligandIndex: number
  label: string
  status: string
  pdbqt: string
  energies: PoseInfo[]
  bestAffinity: number | null
  error: string
}

export interface BatchLigandProgress {
  ligandIndex: number
  label: string
  status: string
  affinity: number | null
  error: string
}

export interface BatchDockingResponse {
  results: BatchLigandResult[]
  total: number
  completed: number
  failed: number
}

export interface BatchJobCreated {
  jobId: string
  status: string
  total: number
}

export interface BatchJobStatus {
  jobId: string
  status: string
  progress: number
  totalLigands: number
  completedLigands: number
  failedLigands: number
  currentLigand: string
  ligands: BatchLigandProgress[]
  error: string | null
  elapsedMs: number | null
}

export interface BatchJobResult {
  jobId: string
  status: string
  results: BatchLigandResult[]
  total: number
  completed: number
  failed: number
  elapsedMs: number | null
}

export interface ProjectBox {
  center: number[]
  size: number[]
}

export interface ProjectDockingConfig {
  scoring: string
  exhaustiveness: number
  nPoses: number
  energyRange: number
  minRmsd: number
  cpu: number
  seed: number
  noRefine: boolean
}

export interface ProjectLigand {
  label: string
  path: string | null
  pdbqtString: string | null
}

export interface ProjectReceptor {
  path: string
  flexPath: string | null
}

export interface ProjectFile {
  formatVersion: string
  createdAt: string
  updatedAt: string
  name: string
  description: string
  receptor: ProjectReceptor | null
  ligands: ProjectLigand[]
  box: ProjectBox | null
  docking: ProjectDockingConfig
  lastJobId: string | null
  results: Record<string, unknown>[]
}

export interface ProjectListEntry {
  path: string
  filename: string
  name: string
  createdAt: string
  updatedAt: string
  description: string
}

export interface WorkspaceInfo {
  path: string
  name: string
  version: number
  createdAt: string
  isValid: boolean
  subdirectories: Record<string, string>
}

export interface WorkspaceInitRequest {
  path: string
  name?: string
}

export interface WorkspaceMigrateRequest {
  targetPath: string
}

export interface WorkspaceSetRequest {
  path: string
}

/**
 * A failure the interface can act on, not just display: the domain error body
 * carries a message, a kind and (for receptor preparation) offending residues.
 */
export interface PreparationFailure {
  message: string
  kind: string
  residues: string[]
}

/** What a file holds, and the evidence the server used to decide. */
export interface Detection {
  kind: 'receptor' | 'ligand'
  reason: 'extension' | 'polymer residues' | 'small molecule'
  atoms: number
  residues: number
  waters: number
  chains: number
  polymerResidues: number
}

export interface InteractionData {
  type: 'hydrogen_bond' | 'hydrophobic' | 'ionic'
  receptorResidue: string
  receptorChain: string
  receptorResSeq: string
  receptorAtom: string
  receptorX: number
  receptorY: number
  receptorZ: number
  ligandAtom: string
  ligandX: number
  ligandY: number
  ligandZ: number
  distance: number
}

/** Native bridge capabilities exposed through QWebChannel. */
export interface DesktopBridge {
  appInfo(): string
  getLanguage(): string
  setLanguage(language: string): boolean
  openFiles(title: string, filters: string, multiple: boolean): string
  saveFile(title: string, suggestedName: string, filters: string): string
  openDirectory(title: string): string
  saveImage(dataUrl: string, suggestedName: string): string
  revealInFileManager(path: string): boolean
  notify(title: string, message: string): void
  quit(): void
}

// --------------------------------------------------------------------------
// molecule library (RCSB PDB)
// --------------------------------------------------------------------------

export interface LibrarySearchRequest {
  query: string
  rows?: number
  start?: number
}

export interface LibraryLigand {
  id: string
  name: string
  formula: string
  molecularWeight: number | null
}

export interface LibraryChain {
  entityId: string
  description: string
  organism: string
  sequenceLength: number
}

export interface LibraryEntry {
  pdbId: string
  title: string
  method: string
  resolution: number | null
  year: number | null
  authors: string[]
  journal: string
  doi: string
  organism: string
  ligands: LibraryLigand[]
  chains: LibraryChain[]
  entityCount: number
  atomCount: number
  molecularWeight: number | null
  moleculeType: 'protein' | 'rna' | 'dna' | 'hybrid' | 'unknown'
}

export interface LibrarySearchResponse {
  entries: LibraryEntry[]
  totalCount: number
}

export interface LibraryFetchRequest {
  pdbId: string
  kind: 'receptor' | 'ligand'
  ligandId?: string
}

export interface LibraryFetchResponse {
  path: string
  name: string
  bytes: number
  pdbId: string
}

export interface LibraryFetchAllRequest {
  pdbId: string
  ligandIds: string[]
}

export interface LibraryFetchAllResponse {
  receptor: LibraryFetchResponse
  ligands: LibraryFetchResponse[]
}
