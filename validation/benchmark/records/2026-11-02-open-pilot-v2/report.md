# VinaStudio validation report

Report schema: 2.1
Generated: 2026-11-02T14:09:16+00:00
Dataset: open-posebusters-pilot-v2 (Open PoseBusters pilot v2 (cofactor-aware))
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

**Summary:** 3 passed · 1 failed · 0 skipped

## Cases

| Case | Status | Best affinity | RMSD | Poses | Error poses | Licence | Reason |
|---|---|---:|---:|---:|---:|---|---|
| 5sb2 | passed | -12.446 | 0.508 | 5 | 0 | CC0-1.0 |  |
| 5sd5 | passed | -8.355 | 0.584 | 9 | 0 | CC0-1.0 |  |
| 5sis | failed | -8.941 | 5.714 | 9 | 0 | CC0-1.0 | best RMSD 5.714 Å exceeds 2.000 Å |
| 6m2b | passed | -10.179 | 1.630 | 9 | 0 | CC0-1.0 |  |

## Provenance

| Case | Reference independent | Reference matches pose | Reference SHA-256 |
|---|---|---|---|
| 5sb2 | True | True | 5813d398b255 |
| 5sd5 | True | True | 353899b7e448 |
| 5sis | True | True | 73a21e117fce |
| 6m2b | True | True | 73eab62f088e |

A pass means: at least one pose, best RMSD within the configured threshold, the reference could be matched for reference-relative checks, no geometry error in any pose, and any configured affinity range met. Warnings are recorded but do not fail a case. Skipped cases mean their optional input files are absent; they are not evidence of success. Restricted datasets are not redistributed with this report.
