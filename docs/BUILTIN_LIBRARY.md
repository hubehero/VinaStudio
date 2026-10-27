# Built-in undergraduate drug library

[简体中文](BUILTIN_LIBRARY.zh-CN.md)

VinaStudio ships a small, offline, editable Catalog library for undergraduate
pharmacology and medicinal-chemistry teaching. It is a **starting point for
structure browsing and docking practice**, not a clinical reference.

## What is included

- **125 small-molecule drugs** covering autonomic, CNS, anaesthetic,
  cardiovascular, respiratory, GI, endocrine, antimicrobial, anticancer,
  anti-inflammatory and anticoagulant teaching categories.
- English INN/common name, a Chinese common name, drug class (English key plus
  Chinese label), PubChem CID, molecular formula and InChIKey.
- Structures are fetched from **PubChem** at build time and verified with
  RDKit; every row parses and its RDKit InChIKey matches PubChem.
- The library is seeded once per workspace. It creates ordinary Catalog
  molecules, a parent Collection with nested broad-class Collections (autonomic,
  CNS, cardiovascular, antimicrobial, etc.) and a Library, so it can be
  renamed, edited, reduced or deleted like any other user data. **Deleting it
  does not recreate it on the next launch.**

## Scientific scope and limits

- Selection favours drugs that appear in standard undergraduate teaching for
  mechanism/class breadth; it is not a formulary and does not include dosing,
  indications, contraindications or clinical recommendations.
- Structures are the PubChem records for the named compound. Salts, hydrates,
  protonation and stereochemical forms may differ from a particular marketed
  product; the structure record is the docking input, not a pharmaceutical
  equivalence claim.
- The seeded source files are **2D SDF** records. They are deliberately not
  ready-to-dock 3D structures: use the normal Catalog preparation step to add
  hydrogens and generate a 3D conformer/PDBQT.
- Some compounds are controlled medicines or toxic reference compounds. They
  are present only as teaching structures; handle and use them according to
  local rules.
- The library is not a curated activity/assay dataset. Docking scores are
  hypotheses for teaching and comparison, not experimental affinities.

## Textbook orientation

The class coverage is aligned with common Chinese and international
undergraduate texts:

- 《药理学》（人民卫生出版社，杨宝峰/陈建国主编）
- 《药物化学》（人民卫生出版社，尤启冬主编）
- Goodman & Gilman's *The Pharmacological Basis of Therapeutics*
- Katzung's *Basic & Clinical Pharmacology*
- Rang & Dale's *Pharmacology*
- Foye's *Principles of Medicinal Chemistry*

These books inform the selection of classes; they are not copied into the
data. The structures and identifiers come from PubChem.

## Data and provenance

- File: `vinastudio/resources/catalog/undergraduate_drugs.csv`
- Molecule source: `PubChem`, with CID and source URL stored per molecule.
- Dataset version: `1` (`catalog_meta` marker `builtin_undergrad_drugs_v1`).
- Re-seeding is opt-in for development with
  `VINASTUDIO_BUILTIN_LIBRARY_SEED=1`; tests disable it so workspaces remain
  deterministic.

## Related documentation

- [Molecule Catalog](MOLECULE_CATALOG.md)
- [User guide](USER_GUIDE.md)
