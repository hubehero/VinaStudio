# Built-in undergraduate drug-target collection

[简体中文](BUILTIN_RECEPTORS.zh-CN.md)

VinaStudio ships an offline, editable collection of **27 drug-target protein
structures** for undergraduate pharmacology and medicinal-chemistry teaching.
They are Catalog molecules of type **receptor**, grouped in a Collection, not
a screening Library: a Library is a ligand input and must not be offered as a
screening ligand set.

## What is included

- Kinases: ABL1 (1IEP), EGFR (1M17), PKA (1ATP), CDK2 (1HCK), Src (2SRC).
- Enzymes: HMG-CoA reductase (1HWK), acetylcholinesterase (1EVE), influenza
  neuraminidase (1B9V), DHFR (1DHF), ACE (1O86), COX-1 (1EQG), COX-2 (5KIR),
  MAO-A (2Z5X), MAO-B (2V5Z).
- Protease: HIV-1 protease (1HSG).
- Nuclear receptors: ERα (1ERE), androgen receptor (1E3G), glucocorticoid
  receptor (1M2Z), PPARγ (2PRG).
- GPCRs: β2-adrenergic (2RH1), M2 muscarinic (3UON), D2 dopamine (6CM4),
  H1 histamine (3RZE), μ-opioid (4DKL).
- Transporter: serotonin transporter SERT (5I6X).
- Ion channels: GABA-A (6D6U), hERG (5VA1).

Each row carries PDB ID, target/gene, target class, organism, chain,
co-crystallised ligand (where present), resolution, method and a construct
note. The **protein MW** shown in the Catalog is calculated from the modelled
polymer residues of the deposited coordinates; it excludes co-crystal ligands,
waters and unresolved residues, and is therefore not the mass of the full gene
product. All PDB files are bundled under
`vinastudio/resources/catalog/receptors/`; source URLs point to RCSB.

## Scientific limits

- These are **experimental structures with constructs**, not necessarily the
  wild-type human protein. Several GPCR entries contain T4-lysozyme or BRIL
  fusions; 5I6X includes Fab partner chains; 6D6U is a multi-subunit GABA-A
  complex; 1M2Z/2PRG include coactivator peptides; 1ATP includes a PKI peptide.
  Preparation keeps protein chains and strips waters/hetero groups by default;
  inspect the construct before interpreting a docking result.
- Resolution ranges from 1.5 Å to 3.92 Å. Lower-resolution and cryo-EM entries
  are included for teaching breadth, not as benchmark-grade docking receptors.
- With the default **“allow residues that fail template matching”** setting on,
  all 27 structures currently prepare; the 13 that fail without it (engineered
  GPCRs, missing-template/terminal residues, and the hERG cryo-EM model) are
  reported with their ignored residues. Turn the default off in Settings if you
  want the stricter Meeko check; a single preparation can always override it.
- A PDB entry is a structure, not a validated disease model or a clinical
  target claim. Docking scores are teaching hypotheses, not measured
  affinities.
- Receptors are seeded once per workspace as ordinary Catalog objects and can
  be renamed, prepared, removed or deleted. Deleting the Collection does not
  recreate it on the next launch.

## Textbook orientation

- 《药理学》（人民卫生出版社，杨宝峰/陈建国主编）
- 《药物化学》（人民卫生出版社，尤启冬主编）
- Goodman & Gilman's *The Pharmacological Basis of Therapeutics*
- Katzung's *Basic & Clinical Pharmacology*
- Rang & Dale's *Pharmacology*
- Foye's *Principles of Medicinal Chemistry*

The books guide target selection; structures and metadata come from RCSB PDB.

## Data and provenance

- File: `vinastudio/resources/catalog/undergraduate_receptors.csv`
- PDB files: `vinastudio/resources/catalog/receptors/*.pdb`
- Source: RCSB PDB (`https://www.rcsb.org/structure/<PDB>`)
- Marker: `builtin_undergrad_receptors_v1`
- Tests disable seeding via `VINASTUDIO_BUILTIN_LIBRARY_SEED=0`; real workspaces
  seed on first Catalog access.
