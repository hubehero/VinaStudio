# Molecule Catalog

> Status: under development on `feat/molecule-catalog-v2`.

The molecule manager is being replaced by a workspace-level **Catalog** backed
by `<workspace>/catalog.sqlite`. The catalog stores identity, metadata,
relationships and library membership; structure files stay on disk.

## Concepts

| Concept | Meaning |
|---|---|
| Molecule | One chemical/structure identity, with one or more source/prepared files |
| Study | A biological context: one or more receptors plus associated ligands |
| Collection | A nested organizational folder; independent of Study |
| Library | An ordered set of catalog molecules used by batch/virtual screening |
| Tag | A many-to-many label; can coexist with Collections |

A molecule's receptor/ligand role belongs to a Study membership, not to the
molecule itself. The same structure can be a ligand in one Study and a receptor
in another.

## Workflow

1. **Import** files (SDF/MOL2/PDB/PDBQT/mmCIF), SMILES, the 2D sketcher,
   built-in samples, RCSB structures/co-crystal ligands, PubChem or ChEMBL
   compounds.
2. The catalog computes identities: ligand InChIKey (parent key kept separately),
   receptor PDB ID or content hash. Duplicate identities merge files and sources.
3. Create a **Study** from selected receptor + ligands, or accept an automatic
   study-pair suggestion derived from a PDB-style filename/source prefix.
4. Organize with Collections and tags; search with free text or field filters.
5. Prepare molecules (receptor/ligand PDBQT) when needed.
6. Create a **Library** from selected ligands/collection/search result.
7. Batch docking queues prepared library members; virtual screening consumes
   the materialized library directory.

## Search

Examples:

```text
imatinib
tag:kinase
source:chembl
study:"1IEP study"
collection:"Kinase leads"
kind:ligand
mw:300-600
```

Search runs on the server with SQLite FTS5 and structured indexes; the UI
does not filter the full molecule list in the browser. Two-character Chinese
queries fall back to a bounded substring search.

## Identity and duplicates

- Full InChIKey is the primary ligand identity.
- `parent_inchi_key` is retained for “possible duplicate” suggestions; salts,
  stereo isomers and tautomers are **not** silently merged.
- Re-importing the same identity appends files/sources and aliases rather than
  creating a second molecule.
- Receptors use a PDB ID when visible in the filename, otherwise a content hash.

## Migration

On first catalog access, the existing `<workspace>/molecules.json` and
`libraries/*/index.json` are imported once. The original manifest is copied to
`molecules.json.pre-catalog` and left in place. Migration is idempotent and
does not delete user files.

## Known boundaries

- Catalog preparation exposes receptor/ligand options and the sequence-based
  flexible-residue picker in a dialog.
- Study/Collection/Library have scope headers with rename, member removal,
  deletion, collection membership and a primary-receptor switch.
- Saved searches, source/tag/status facet chips, sort, page size,
  select-all-current-results and column visibility are available. The table
  virtualises rows with `ElTableV2`; the server still returns bounded pages, so
  paging remains the way to reach later rows.
- Screening shows the catalog library display name in the library, run and
  history views while retaining the stable directory id for requests; clicking
  a ranking row opens the per-ligand result (scores, SMILES, elapsed time and
  output directory).
- Catalog 1iep has been exercised through preparation, Study → docking and an
  actual catalog-library virtual screening run.

## For developers

- Core: `vinastudio/core/catalog/` (`db`, `store`, `query`, `identity`,
  `migrate`, `suggest`, `library`)
- API: `vinastudio/server/routers/catalog.py`
- UI: `web/src/components/panels/catalog/MoleculeCatalogView.vue`
- Contract types: `web/src/types/api.ts`
- Migration is one-way; do not re-introduce a second write path to
  `molecules.json`.

