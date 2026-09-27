/** All 118 elements with factual period/group placement (task book 4.4).

    Rows/columns are the standard periodic-table positions: rows 1-7 are the
    periods, rows 9/10 hold the lanthanides/actinides (columns 4-18), and
    (6,3)/(7,3) are placeholder cells for the two f-series.  The grid renders
    straight from these coordinates, so a wrong entry shows as a visibly
    wrong cell; the count, the 1..118 z sequence and cell uniqueness are
    asserted in tests/unit/test_sketch_chem.py
    (test_periodic_table_source_lists_all_elements).
*/

export interface TableElement {
  z: number
  symbol: string
  /** CSS grid row: 1-7 periods, 9 lanthanides, 10 actinides. */
  row: number
  /** CSS grid column: 1-18. */
  col: number
}

export const PERIODIC_TABLE: TableElement[] = [
  { z: 1, symbol: 'H', row: 1, col: 1 },
  { z: 2, symbol: 'He', row: 1, col: 18 },

  { z: 3, symbol: 'Li', row: 2, col: 1 },
  { z: 4, symbol: 'Be', row: 2, col: 2 },
  { z: 5, symbol: 'B', row: 2, col: 13 },
  { z: 6, symbol: 'C', row: 2, col: 14 },
  { z: 7, symbol: 'N', row: 2, col: 15 },
  { z: 8, symbol: 'O', row: 2, col: 16 },
  { z: 9, symbol: 'F', row: 2, col: 17 },
  { z: 10, symbol: 'Ne', row: 2, col: 18 },

  { z: 11, symbol: 'Na', row: 3, col: 1 },
  { z: 12, symbol: 'Mg', row: 3, col: 2 },
  { z: 13, symbol: 'Al', row: 3, col: 13 },
  { z: 14, symbol: 'Si', row: 3, col: 14 },
  { z: 15, symbol: 'P', row: 3, col: 15 },
  { z: 16, symbol: 'S', row: 3, col: 16 },
  { z: 17, symbol: 'Cl', row: 3, col: 17 },
  { z: 18, symbol: 'Ar', row: 3, col: 18 },

  { z: 19, symbol: 'K', row: 4, col: 1 },
  { z: 20, symbol: 'Ca', row: 4, col: 2 },
  { z: 21, symbol: 'Sc', row: 4, col: 3 },
  { z: 22, symbol: 'Ti', row: 4, col: 4 },
  { z: 23, symbol: 'V', row: 4, col: 5 },
  { z: 24, symbol: 'Cr', row: 4, col: 6 },
  { z: 25, symbol: 'Mn', row: 4, col: 7 },
  { z: 26, symbol: 'Fe', row: 4, col: 8 },
  { z: 27, symbol: 'Co', row: 4, col: 9 },
  { z: 28, symbol: 'Ni', row: 4, col: 10 },
  { z: 29, symbol: 'Cu', row: 4, col: 11 },
  { z: 30, symbol: 'Zn', row: 4, col: 12 },
  { z: 31, symbol: 'Ga', row: 4, col: 13 },
  { z: 32, symbol: 'Ge', row: 4, col: 14 },
  { z: 33, symbol: 'As', row: 4, col: 15 },
  { z: 34, symbol: 'Se', row: 4, col: 16 },
  { z: 35, symbol: 'Br', row: 4, col: 17 },
  { z: 36, symbol: 'Kr', row: 4, col: 18 },

  { z: 37, symbol: 'Rb', row: 5, col: 1 },
  { z: 38, symbol: 'Sr', row: 5, col: 2 },
  { z: 39, symbol: 'Y', row: 5, col: 3 },
  { z: 40, symbol: 'Zr', row: 5, col: 4 },
  { z: 41, symbol: 'Nb', row: 5, col: 5 },
  { z: 42, symbol: 'Mo', row: 5, col: 6 },
  { z: 43, symbol: 'Tc', row: 5, col: 7 },
  { z: 44, symbol: 'Ru', row: 5, col: 8 },
  { z: 45, symbol: 'Rh', row: 5, col: 9 },
  { z: 46, symbol: 'Pd', row: 5, col: 10 },
  { z: 47, symbol: 'Ag', row: 5, col: 11 },
  { z: 48, symbol: 'Cd', row: 5, col: 12 },
  { z: 49, symbol: 'In', row: 5, col: 13 },
  { z: 50, symbol: 'Sn', row: 5, col: 14 },
  { z: 51, symbol: 'Sb', row: 5, col: 15 },
  { z: 52, symbol: 'Te', row: 5, col: 16 },
  { z: 53, symbol: 'I', row: 5, col: 17 },
  { z: 54, symbol: 'Xe', row: 5, col: 18 },

  { z: 55, symbol: 'Cs', row: 6, col: 1 },
  { z: 56, symbol: 'Ba', row: 6, col: 2 },
  { z: 72, symbol: 'Hf', row: 6, col: 4 },
  { z: 73, symbol: 'Ta', row: 6, col: 5 },
  { z: 74, symbol: 'W', row: 6, col: 6 },
  { z: 75, symbol: 'Re', row: 6, col: 7 },
  { z: 76, symbol: 'Os', row: 6, col: 8 },
  { z: 77, symbol: 'Ir', row: 6, col: 9 },
  { z: 78, symbol: 'Pt', row: 6, col: 10 },
  { z: 79, symbol: 'Au', row: 6, col: 11 },
  { z: 80, symbol: 'Hg', row: 6, col: 12 },
  { z: 81, symbol: 'Tl', row: 6, col: 13 },
  { z: 82, symbol: 'Pb', row: 6, col: 14 },
  { z: 83, symbol: 'Bi', row: 6, col: 15 },
  { z: 84, symbol: 'Po', row: 6, col: 16 },
  { z: 85, symbol: 'At', row: 6, col: 17 },
  { z: 86, symbol: 'Rn', row: 6, col: 18 },

  { z: 87, symbol: 'Fr', row: 7, col: 1 },
  { z: 88, symbol: 'Ra', row: 7, col: 2 },
  { z: 104, symbol: 'Rf', row: 7, col: 4 },
  { z: 105, symbol: 'Db', row: 7, col: 5 },
  { z: 106, symbol: 'Sg', row: 7, col: 6 },
  { z: 107, symbol: 'Bh', row: 7, col: 7 },
  { z: 108, symbol: 'Hs', row: 7, col: 8 },
  { z: 109, symbol: 'Mt', row: 7, col: 9 },
  { z: 110, symbol: 'Ds', row: 7, col: 10 },
  { z: 111, symbol: 'Rg', row: 7, col: 11 },
  { z: 112, symbol: 'Cn', row: 7, col: 12 },
  { z: 113, symbol: 'Nh', row: 7, col: 13 },
  { z: 114, symbol: 'Fl', row: 7, col: 14 },
  { z: 115, symbol: 'Mc', row: 7, col: 15 },
  { z: 116, symbol: 'Lv', row: 7, col: 16 },
  { z: 117, symbol: 'Ts', row: 7, col: 17 },
  { z: 118, symbol: 'Og', row: 7, col: 18 },

  { z: 57, symbol: 'La', row: 9, col: 4 },
  { z: 58, symbol: 'Ce', row: 9, col: 5 },
  { z: 59, symbol: 'Pr', row: 9, col: 6 },
  { z: 60, symbol: 'Nd', row: 9, col: 7 },
  { z: 61, symbol: 'Pm', row: 9, col: 8 },
  { z: 62, symbol: 'Sm', row: 9, col: 9 },
  { z: 63, symbol: 'Eu', row: 9, col: 10 },
  { z: 64, symbol: 'Gd', row: 9, col: 11 },
  { z: 65, symbol: 'Tb', row: 9, col: 12 },
  { z: 66, symbol: 'Dy', row: 9, col: 13 },
  { z: 67, symbol: 'Ho', row: 9, col: 14 },
  { z: 68, symbol: 'Er', row: 9, col: 15 },
  { z: 69, symbol: 'Tm', row: 9, col: 16 },
  { z: 70, symbol: 'Yb', row: 9, col: 17 },
  { z: 71, symbol: 'Lu', row: 9, col: 18 },

  { z: 89, symbol: 'Ac', row: 10, col: 4 },
  { z: 90, symbol: 'Th', row: 10, col: 5 },
  { z: 91, symbol: 'Pa', row: 10, col: 6 },
  { z: 92, symbol: 'U', row: 10, col: 7 },
  { z: 93, symbol: 'Np', row: 10, col: 8 },
  { z: 94, symbol: 'Pu', row: 10, col: 9 },
  { z: 95, symbol: 'Am', row: 10, col: 10 },
  { z: 96, symbol: 'Cm', row: 10, col: 11 },
  { z: 97, symbol: 'Bk', row: 10, col: 12 },
  { z: 98, symbol: 'Cf', row: 10, col: 13 },
  { z: 99, symbol: 'Es', row: 10, col: 14 },
  { z: 100, symbol: 'Fm', row: 10, col: 15 },
  { z: 101, symbol: 'Md', row: 10, col: 16 },
  { z: 102, symbol: 'No', row: 10, col: 17 },
  { z: 103, symbol: 'Lr', row: 10, col: 18 },
]

// ---------------------------------------------------------------------------
// Heterocycle ring templates (task book 26 §9)
// ---------------------------------------------------------------------------

export interface HeteroTemplate {
  /** Stable id for the active-state check and data-test keys. */
  id: string
  size: number
  /** Kekulé alternation (true) vs all-single (false). */
  benzene: boolean
  /** Vertex symbols in ring order; vertex 0 sits at the top on free placement
      and is the first shared vertex on fusion (shared vertices keep the
      existing atom's symbol). */
  symbols: string[]
  /** i18n key for the palette label/tooltip. */
  labelKey: string
}

/** Pyridine/piperidine/pyrrole/furan/thiophene/morpholine (task book 26 §9). */
export const HETEROCYCLE_TEMPLATES: HeteroTemplate[] = [
  { id: 'pyridine', size: 6, benzene: true, symbols: ['N', 'C', 'C', 'C', 'C', 'C'], labelKey: 'sketcher.ringPyridine' },
  { id: 'piperidine', size: 6, benzene: false, symbols: ['N', 'C', 'C', 'C', 'C', 'C'], labelKey: 'sketcher.ringPiperidine' },
  { id: 'pyrrole', size: 5, benzene: true, symbols: ['N', 'C', 'C', 'C', 'C'], labelKey: 'sketcher.ringPyrrole' },
  { id: 'furan', size: 5, benzene: true, symbols: ['O', 'C', 'C', 'C', 'C'], labelKey: 'sketcher.ringFuran' },
  { id: 'thiophene', size: 5, benzene: true, symbols: ['S', 'C', 'C', 'C', 'C'], labelKey: 'sketcher.ringThiophene' },
  { id: 'morpholine', size: 6, benzene: false, symbols: ['N', 'C', 'C', 'O', 'C', 'C'], labelKey: 'sketcher.ringMorpholine' },
]
