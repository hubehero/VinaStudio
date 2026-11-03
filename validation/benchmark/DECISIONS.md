# Benchmark Decisions

**Date:** 2026-11-02  
**Status:** binding for the confirmatory open benchmark

## D1 — pilot v1/v2 are exploratory

`records/2026-11-02-open-pilot/` (v1) and
`records/2026-11-02-open-pilot-v2/` (v2) document an engineering pilot. They are
not a confirmatory accuracy claim and are not rewritten.

## D2 — 5SIS remains a known failure

5SIS/JSM stays in the pilot record as a failure. It is not excluded from the
record, not relabelled as a pass, and not tuned with a per-case box, seed,
exhaustiveness or cofactor list.

## D3 — primary 12 exclude all four pilot targets

The confirmatory target set excludes `5SB2`, `5SD5`, `5SIS` and `6M2B`. This is
because the pilot informed the preparation policy, not because 5SIS failed.

The confirmatory set is a fresh, pre-registered 12-target open benchmark. Pilot
cases remain available as an exploratory appendix.

## D4 — preparation policy is automatic

All confirmatory targets use the same rule:

- native-ligand centroid, 22 Å box;
- `defaultAltloc = "A"`, with any residue lacking A or failing template
  matching recorded after explicit exclusion;
- delete water and the pre-registered cryoprotectant/buffer list;
- keep non-water HETATM groups within 6.0 Å of a native-ligand heavy atom;
- record every kept/deleted group;
- reference graph from CCD `*_ideal.sdf`, coordinates from PDB HETATM;
- reject a reference whose bond lengths are implausible.

No per-case cofactor list is allowed in the confirmatory manifest.

## D5 — no result-dependent changes

After the 12-target list is frozen:

- no target may be replaced because of its docking result;
- no seed, box, threshold or cofactor may be adjusted per target;
- failures and skips are retained;
- a protocol change creates a new protocol and a new record.

## D6 — claims

The primary result, when completed, covers only the 12 pre-registered open
targets. It is not a universal docking-accuracy claim, an affinity prediction
claim, or an enrichment claim. 5SIS is not included in the primary success rate.
