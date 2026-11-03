# Benchmark Data Sources and Licence Notes

Reviewed **2026-11-02** against the official pages listed below. This is a
compliance record, not legal advice. Re-check the current terms before a public
release and record the access date in the manifest.

## Decision table

| ID | Source | What may be used | Licence / terms | Redistributable | Repository treatment |
|---|---|---|---|---|---|
| `PDB` | wwPDB / RCSB PDB | Structures, coordinates, PDB API files | CC0 1.0 | Yes | `open`; attribute original authors where possible |
| `PoseBusters-Benchmark` | degrado-lab/PoseBusters-Benchmark | PDB-derived benchmark structures, FASTA, ID list | MIT repository licence; structural data from PDB | Yes | `open`; keep `LICENSE` and citation |
| `PDBbind` | PDBbind / PDBbind+ | Affinity labels and prepared complexes | Registration/user agreement; redistribution prohibited without permission | No | `local-restricted`; user registers and downloads |
| `CASF` | PDBbind+ CASF packages | Core set and scoring benchmark | Same PDBbind user agreement | No | `local-restricted`; do not mirror |
| `DUD-E` | DUD-E / docking.org | Actives, decoys, target lists | Free to use; docking.org forbids major redistribution without permission | No | `local-restricted`; publish metrics only |
| `ZINC` | ZINC / docking.org | Screening libraries | Free to use; no major redistribution without permission | No | `local-restricted` |
| `ChEMBL` | EMBL-EBI ChEMBL | Bioactivity and compound records | CC BY-SA 3.0; attribution and share-alike | Yes, with conditions | Deferred `attribution` layer; separate data licence |
| `BindingDB` | BindingDB | Curated affinities; imported ChEMBL subset | BindingDB-curated data CC BY 3.0; ChEMBL-derived data CC BY-SA 3.0 | Per record | Deferred; source-level provenance required |
| `PubChem` | NCBI PubChem | Compounds and bioassays | Record-level provenance; do not assume one licence for all records | Per record | Not a benchmark label source without record review |
| `LIT-PCBA` | LIT-PCBA | PubChem-derived screening sets | Download page does not state a single clear licence | Unconfirmed | `unconfirmed`; do not include |
| `CrossDocked2020` | CrossDocked2020 derivatives | Pose/training data | Derivative chain and licence unclear | Unconfirmed | `unconfirmed`; do not include |
| `Astex Diverse` | Astex Diverse Set | Structures | Terms not confirmed for redistribution | Unconfirmed | `unconfirmed`; do not include |

## Critical distinctions

1. **PDB coordinates are CC0; PDBbind affinity labels are not.** A PDB structure
   downloaded from RCSB can be redistributed with attribution. A PDBbind
   prepared complex or affinity table cannot be mirrored under the same claim.
2. **“Free to use” is not “free to redistribute.”** DUD-E and files.docking.org
   describe free use but explicitly restrict major redistribution. The benchmark
   may publish metrics; it may not publish the library.
3. **ChEMBL CC BY-SA is share-alike.** If ChEMBL-derived labels enter a data
   directory, that directory must retain the CC BY-SA notice and attribution;
   it cannot be relicensed as MIT.
4. **BindingDB is mixed-licence.** Treat each record according to its source;
   do not label the whole download as CC BY.
5. **PubChem is record-level.** Some records carry third-party provenance and
   restrictions. Keep the source and licence metadata with any selected record.
6. **Derived poses can still be restricted.** A docked pose generated from a
   PDBbind ligand, or an image of it, is not automatically free to publish just
   because the software is open source.

## Acquisition rules

- Use official sites or official APIs; do not use third-party mirrors.
- Do not automate registration, login, CAPTCHA or licence acceptance.
- Do not store credentials, cookies or tokens in the repository.
- Record URL, version/release, access date and SHA-256 in the manifest.
- Verify every downloaded file before use; reject empty or HTML error pages.
- Keep restricted data outside the repository (`.benchmark-data/restricted/`)
  and never place it under `validation/benchmark/data/`.
- Publish aggregate metrics and hashes for restricted data only.

## Source links

- [RCSB PDB Usage Policies](https://www.rcsb.org/pages/usage-policy)
- [wwPDB Usage Policies](https://www.wwpdb.org/about/usage-policies)
- [PDBbind+ License Agreement](https://www.pdbbind-plus.org.cn/termofuse)
- [BindingDB 2024 paper: PDBbind redistribution note](https://academic.oup.com/nar/article/53/D1/D1633/7906836)
- [PoseBusters-Benchmark (MIT)](https://github.com/degrado-lab/PoseBusters-Benchmark)
- [ChEMBL licensing](https://chembl.github.io/chembl-licensing/)
- [BindingDB licensing](https://ww.bindingdb.org/rwd/bind/info.jsp)
- [DUD-E](https://dude.docking.org/)
- [files.docking.org redistribution terms](https://www.decoys.docking.org/)
- [UCSF ZINC license](https://wiki.docking.org/index.php?title=UCSF_ZINC_License)
- [LIT-PCBA](https://drugdesign.unistra.fr/LIT-PCBA/)
- [PubChem downloads and licensing considerations](https://pubchem.ncbi.nlm.nih.gov/docs/downloads)

## Attribution text to use

For PDB-derived case data:

> Structures are derived from the RCSB PDB (CC0 1.0). Original PDB entry
> authors are cited in the benchmark manifest.

For PoseBusters-Benchmark:

> Benchmark target list and derived structures from degrado-lab/PoseBusters-Benchmark,
> MIT licence. See the upstream repository for its citation and notices.

For a future ChEMBL-derived layer:

> ChEMBL data is from https://www.ebi.ac.uk/chembl, version &lt;release&gt;,
> licensed CC BY-SA 3.0.
