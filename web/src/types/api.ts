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
  rendering?: {
    /** VINASTUDIO_SOFTWARE_RENDER=1 was set when the server started. */
    softwareRenderRequested: boolean
  }
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

export type ArtifactKind = 'pdbqt' | 'pdb' | 'sdf' | 'json' | 'log' | 'text' | 'zip'

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

/** Body of POST /api/ligand/from-smiles — single paste or one-per-line batch. */
export interface LigandFromSmilesRequest {
  smiles?: string | null
  smilesList?: string[] | null
  name?: string | null
  options?: Partial<LigandOptions>
}

/** One ligand built from SMILES: path + inspect preview + full preparation. */
export interface LigandFromSmilesItem {
  path: string
  name: string
  bytes: number
  preview: LigandPreview
  preparation: LigandPreparation
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
  createdAt: number
  label: string
  bestAffinity: number | null
  isBatch: boolean
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

/** Bundle members the export-bundle endpoint can pack (TASK-08). */
export type BundleMember = 'sdf' | 'csv' | 'config' | 'svg2d' | 'html'

export interface ExportBundleRequest {
  /** Exactly these files end up in the zip; also gates the report's inline SVG. */
  include: BundleMember[]
  /** Serialized 2D interaction diagram; omitted when the caller cannot supply one. */
  svg2d?: string
  /** Report language; follows the interface language. */
  lang: 'zh-CN' | 'en-US'
}

// ── pose geometric validation (TASK-02, migrated from api/http.ts) ─────────

export type PoseFindingSeverity = 'error' | 'warning'

export interface PoseFinding {
  code: string
  severity: PoseFindingSeverity
  messageKey: string
  detail: Record<string, unknown>
}

export interface PoseValidationItem {
  poseIndex: number
  findings: PoseFinding[]
  worstSeverity: PoseFindingSeverity | null
}

export interface ValidatePosesRequest {
  poseIndex?: number | null
  center?: [number, number, number] | null
  size?: [number, number, number] | null
  referenceSdfPath?: string | null
  enabled?: string[] | null
}

export interface ValidatePosesResponse {
  jobId: string
  poses: PoseValidationItem[]
  thresholds: Record<string, number>
  checksRun: string[]
}

// ── redocking RMSD vs a co-crystal reference (TASK-03, migrated from http.ts) ──

export interface RmsdRequestBody {
  referencePath?: string
  referencePdbqt?: string
  threshold?: number
}

export interface RmsdResponse {
  jobId: string
  values: number[]
  threshold: number
  successRate: number
  /** False = different chemical structure (warn, never reject); null = unknown. */
  structureMatch: boolean | null
}

// ── pose clustering (TASK-04, migrated from api/http.ts) ────────────────────

export interface ClusterItem {
  /** 0-based pose indices, file order. */
  members: number[]
  /** 0-based index of the representative pose (smallest mean distance). */
  centroid: number
  size: number
  meanRmsd: number
}

export interface ClusterResponse {
  jobId: string
  cutoff: number
  clusters: ClusterItem[]
  nClusters: number
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

/** Format 1.1: a pointer to a job's artifacts, never the results themselves. */
export interface ProjectResultRef {
  jobId: string
  label: string
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
  results: ProjectResultRef[]
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

/** One atom of the 2D interaction-map depiction (TASK-06).

 * `x`/`y` are the unit-square layout (aspect preserved, y up); `x3`/`y3`/`z3`
 * snapshot the original 3D site — contact rows map to depiction atoms by
 * these coordinates because RDKit restores hydrogens the PDBQT file lacks
 * (index alignment fails, coordinate alignment does not). Null when the
 * source carried no conformer.
 */
export interface DepictAtom {
  idx: number
  x: number
  y: number
  x3: number | null
  y3: number | null
  z3: number | null
  symbol: string
  charge: number
  aromatic: boolean
}

/** A bond as restored from SMILES/SDF chemistry — never guessed from geometry. */
export interface DepictBond {
  a1: number
  a2: number
  /** RDKit order: 1, 1.5 (aromatic), 2, … */
  order: number
  aromatic: boolean
}

export interface DepictData {
  atoms: DepictAtom[]
  bonds: DepictBond[]
}

export interface AnalyzeInteractionsRequest {
  receptorPath: string
  ligandPath?: string
  ligandPdbqtString?: string
  distanceCutoff?: number
}

export interface AnalyzeInteractionsResponse {
  interactions: InteractionData[]
  count: number
  /** null when bond orders could not be restored (e.g. PDBQT without REMARK SMILES). */
  depict: DepictData | null
}

// --------------------------------------------------------------------------
// 2D sketch editor (contract with POST /api/chem/sketch/analyze)
// --------------------------------------------------------------------------

/** One atom as drawn: scene pixels (y grows downward), editor-assigned id. */
export interface SketchAtomInput {
  id: number
  symbol: string
  x: number
  y: number
  charge: number
  radical: number
}

export interface SketchBondInput {
  a1: number
  a2: number
  /** Kekule order: 1, 2, 3 (1.5 accepted by the backend, no tool emits it). */
  order: number
  /** 0 none, 1 wedge, 2 hash — drawn at the a1 end. */
  stereo: number
}

export interface SketchAnalyzeRequest {
  atoms: SketchAtomInput[]
  bonds: SketchBondInput[]
}

export interface SketchRingInfo {
  atomIds: number[]
  /** Mean of input pixel positions — drawn in scene space, not Angstrom. */
  center: [number, number]
}

export interface SketchAnalyzeResponse {
  /** Canonical isomeric SMILES; null while the drawing is chemically invalid. */
  smiles: string | null
  /** Editor atom id → implicit hydrogen count (only ids with count > 0). */
  implicitH: Record<number, number>
  /** Editor atom ids that failed the chemistry check (red frames). */
  problems: number[]
  rings: SketchRingInfo[]
  /** Human explanation when smiles is null. */
  error: string | null
}

export interface SketchCleanupResponse {
  /** Editor atom id → [x, y] in Angstrom, chemical frame (y grows up). */
  positions: Record<number, [number, number]>
}

/** Whole-drawing answer for POST /api/chem/sketch/layout.

    Structurally the analyze input shapes, but x/y are Angstrom on the
    chemical frame (cleanup convention), **not** scene pixels — the importer
    converts with the shared Å→px helper before committing.
 */
export interface SketchLayoutResponse {
  atoms: SketchAtomInput[]
  bonds: SketchBondInput[]
}

/** Native bridge capabilities exposed through QWebChannel.

    QWebChannel wraps every slot that has a ``result`` return type in a
    Promise, so all non-void methods return ``Promise<T>`` on the JS side.
 */
export interface DesktopBridge {
  appInfo(): Promise<string>
  getLanguage(): Promise<string>
  setLanguage(language: string): Promise<boolean>
  openFiles(title: string, filters: string, multiple: boolean): Promise<string>
  saveFile(title: string, suggestedName: string, filters: string): Promise<string>
  openDirectory(title: string): Promise<string>
  saveImage(dataUrl: string, suggestedName: string): Promise<string>
  /** Write UTF-8 text to a path the caller already chose; false on failure. */
  writeTextFile(path: string, content: string): Promise<boolean>
  revealInFileManager(path: string): Promise<boolean>
  openUrl(url: string): Promise<boolean>
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
