# Confirmatory 4-target smoke — 2026-11-02

**Status:** T06 preparation smoke; not the primary 12 × 5 result.
**Manifest:** `validation/benchmark/manifests/open-posebusters-v1.json`
**Targets:** 8DHG, 7ZU2, 8AEM, 7NPL (first four frozen confirmatory targets)
**Seed:** 42

## Result

| Target | Status | Affinity | RMSD | Poses |
|---|---|---:|---:|---:|
| `8dhg` | passed | −12.045 | 0.503 Å | 5 |
| `7zu2` | passed | −10.543 | 0.603 Å | 5 |
| `8aem` | passed | −7.737 | 0.470 Å | 5 |
| `7npl` | passed | −13.798 | 0.307 Å | 5 |

**4/4 passed.** This validates the frozen manifest, data hashes, reference
construction, cofactor/altloc preparation and reporting path. It is not the
primary 12-target result and does not include the other eight targets or five
seeds.

Raw structures live under gitignored `.benchmark-data/`; the record contains
only the report and hashes.
