# VinaStudio validation report

Report schema: 2.1
Generated: 2026-11-02T14:43:29+00:00
Dataset: open-posebusters-v1 (Open PoseBusters confirmatory 12)
Dataset licences: CC0-1.0, MIT; redistributable: yes

This is a reproducible redocking check, not an accuracy ranking. The geometry checks are a PoseBusters-style subset, not the official suite.

## Environment

| Item | Value |
|---|---|
| appVersion | 0.6.6 |
| python | 3.12.14 |
| platform | Linux 7.0.0-42-generic (x86_64) |
| cpuCount | 8 |
| vina | 1.2.7 |
| meeko | 0.8.0 |
| rdkit | 2026.9.1 |
| numpy | 2.5.4 |
| scipy | 1.18.1 |
| gemmi | 0.7.5 |
| gitCommit | 94ccd739d45aa261558691ffa13af022d320b2dc |
| gitDirty | yes |
| engineBackend | vina |
| engineReason | the vina Python module is installed |

**Summary:** 4 passed · 0 failed · 0 skipped

## Cases

| Case | Status | Best affinity | RMSD | Poses | Error poses | Licence | Reason |
|---|---|---:|---:|---:|---:|---|---|
| 8dhg | passed | -12.045 | 0.503 | 2 | 0 | CC0-1.0 |  |
| 7zu2 | passed | -10.543 | 0.603 | 5 | 0 | CC0-1.0 |  |
| 8aem | passed | -7.737 | 0.470 | 6 | 0 | CC0-1.0 |  |
| 7npl | passed | -13.798 | 0.307 | 4 | 0 | CC0-1.0 |  |

## Provenance

| Case | Reference independent | Reference matches pose | Reference SHA-256 |
|---|---|---|---|
| 8dhg | True | True | 60839fa5abf8 |
| 7zu2 | True | True | 7ba878a825e5 |
| 8aem | True | True | 7144ebddfb28 |
| 7npl | True | True | 518ce06908b0 |

A pass means: at least one pose, best RMSD within the configured threshold, the reference could be matched for reference-relative checks, no geometry error in any pose, and any configured affinity range met. Warnings are recorded but do not fail a case. Skipped cases mean their optional input files are absent; they are not evidence of success. Restricted datasets are not redistributed with this report.
