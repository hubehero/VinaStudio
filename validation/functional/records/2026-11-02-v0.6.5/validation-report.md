# VinaStudio validation report

Report schema: 2.0
Generated: 2026-11-02T10:20:25+00:00

This is a reproducible redocking check, not an accuracy ranking. The geometry checks are a PoseBusters-style subset, not the official suite.

## Environment

| Item | Value |
|---|---|
| appVersion | 0.6.5 |
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
| gitDirty | no |
| engineBackend | vina |
| engineReason | the vina Python module is installed |

**Summary:** 1 passed · 0 failed · 0 skipped

## Cases

| Case | Status | Best affinity | RMSD | Poses | Error poses | Reason |
|---|---|---:|---:|---:|---:|---|
| 1iep | passed | -13.286 | 0.353 | 5 | 0 |  |

## Provenance

| Case | Reference independent | Reference matches pose | Reference SHA-256 |
|---|---|---|---|
| 1iep | True | True | 1bcc3920c107 |

A pass means: at least one pose, best RMSD within the configured threshold, the reference could be matched for reference-relative checks, no geometry error in any pose, and any configured affinity range met. Warnings are recorded but do not fail a case. Skipped cases mean their optional input files are absent; they are not evidence of success.
