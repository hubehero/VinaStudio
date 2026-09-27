import type {
  Artifact,
  LigandOptions,
  LigandPreview,
  LigandReport,
  PreparationFailure,
  ReceptorOptions,
  ReceptorPreview,
  ReceptorReport,
} from './api'

export type MoleculeType = 'receptor' | 'ligand' | 'unknown'
export type DetectionSource = 'extension' | 'content' | 'user'
export type DetectionReason = 'extension' | 'polymer residues' | 'small molecule'

export type MoleculeStatus =
  | 'uploaded'
  | 'inspecting'
  | 'inspected'
  | 'preparing'
  | 'prepared'
  | 'error'


export interface MoleculeItem {
  id: string
  name: string
  path: string
  size: number
  detectedType: MoleculeType
  detectionConfidence: number
  detectionSource: DetectionSource
  /** Why the server called it that, when it had to read the file. */
  detectionReason: DetectionReason | null
  assignedType: MoleculeType | null
  status: MoleculeStatus
  preview: LigandPreview | ReceptorPreview | null
  /** Set once prepared; the shape matches the molecule's kind. */
  report: LigandReport | ReceptorReport | null
  artifacts: Artifact[]
  pdbqt: string | null
  error: PreparationFailure | null
  receptorOptions: ReceptorOptions
  ligandOptions: LigandOptions
  /** Group ID — molecules from the same PDB entry share this. */
  groupId: string | null
  /** Display name for the group (e.g. PDB ID). */
  groupName: string | null
  /** User-assigned aliases (e.g. Chinese names). */
  aliases: string[]
  /** User-assigned category (e.g. '激酶', '蛋白酶'). */
  category: string | null
}

/** A receptor with its associated ligands, for grouped display. */
export interface MoleculeGroup {
  id: string
  name: string
  receptor: MoleculeItem | null
  ligands: MoleculeItem[]
}

// ── manifest (persistent storage) ───────────────────────────────────────────

/** Wire format for a single molecule in the manifest. */
export interface MoleculeManifestEntry {
  id: string
  name: string
  path: string
  size: number
  detectedType: MoleculeType
  detectionConfidence: number
  detectionSource: DetectionSource
  detectionReason: string | null
  assignedType: MoleculeType | null
  status: MoleculeStatus
  preview: unknown
  report: unknown
  artifacts: Artifact[]
  pdbqt: string | null
  error: unknown
  receptorOptions: ReceptorOptions
  ligandOptions: LigandOptions
  groupId: string | null
  groupName: string | null
  aliases: string[]
  category: string | null
  mtime: number | null
  createdAt: string
  updatedAt: string
}

/** Workspace-level molecule manifest. */
export interface MoleculeManifest {
  formatVersion: string
  updatedAt: string
  molecules: MoleculeManifestEntry[]
}

export function getEffectiveType(mol: MoleculeItem): MoleculeType {
  return mol.assignedType ?? mol.detectedType
}
