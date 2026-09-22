import { ApiError } from '@/api/http'
import type {
  DomainErrorBody,
  LigandOptions,
  PreparationFailure,
  ReceptorOptions,
} from '@/types/api'

/**
 * Values and helpers the preparation flow needs in more than one place.
 *
 * The Molecule Manager prepares through the shared endpoints; one copy of the
 * defaults keeps every request starting from the same options, and one copy of
 * the error translation shows the same failure the same way everywhere.
 */

//: Defaults mirror the backend models so the first request is already correct.
export const DEFAULT_LIGAND_OPTIONS: LigandOptions = {
  optimiseGeometry: true,
  embedSeed: 0xf00d,
  rigidMacrocycles: false,
  flexibleAmides: false,
  hydrate: false,
  doubleBondPenalty: 50,
}

export const DEFAULT_RECEPTOR_OPTIONS: ReceptorOptions = {
  deleteWaters: true,
  deleteHetero: true,
  flexibleResidues: [],
  allowBadResidues: false,
  normaliseAtomOrder: true,
}

export function describeFailure(error: unknown): PreparationFailure {
  if (error instanceof ApiError) {
    const body = (error.detail ?? {}) as Partial<DomainErrorBody>
    return {
      message: typeof body.detail === 'string' ? body.detail : error.message,
      kind: typeof body.kind === 'string' ? body.kind : 'ApiError',
      residues: Array.isArray(body.residues) ? body.residues : [],
    }
  }
  return {
    message: error instanceof Error ? error.message : String(error),
    kind: 'Unknown',
    residues: [],
  }
}
