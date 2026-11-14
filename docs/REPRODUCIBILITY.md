# Reproducibility and release verification

**English** · [简体中文](REPRODUCIBILITY.zh-CN.md)

This page describes what a VinaStudio release proves, how to verify a downloaded
asset, and where the software-validation evidence lives. It is deliberately
separate from the scientific claims: a reproducible build is not a claim of
general docking accuracy.

## Release provenance

From v0.7.0 onward, each GitHub Release carries:

| Asset | Purpose |
|---|---|
| `SHA256SUMS` | SHA-256 for the Linux tarball, `.deb` and Windows installer |
| `BUILD-MANIFEST.json` | tag, source commit, CI run URL, build date, Python version, asset sizes and SHA-256 values |

The manifest is written by the tagged CI run and uploaded with the artifacts.
The v0.7.0 manifest was reconstructed from the published GitHub asset metadata;
releases built after the workflow change generate it in CI. It is a provenance
record, not a signature. The Windows installer is still unsigned, so SmartScreen
can still prompt.

## Verify a release

Download `SHA256SUMS` and the asset you intend to run, then verify the checksum
before executing anything:

```bash
sha256sum -c SHA256SUMS
```

`BUILD-MANIFEST.json` records the same hashes plus the tag, commit and workflow
run. Compare its `tag` and `commit` with the release page; if they do not match,
do not use the asset.

## Re-run the software checks

The **release tree intentionally does not ship the test suite**; this keeps the
published source small and avoids distributing fixtures that are not part of the
runtime. The full pytest suite runs in the development source tree:

```bash
uv sync --extra dev
uv run pytest -q
uv run ruff check .
pnpm -C web typecheck
pnpm -C web test
```

In the release tree, the lightweight public backend smoke is:

```bash
uv run python validation/ci/smoke.py
```

The smoke covers health, workspace setup, file detection, ligand preparation,
box calculation and read-only diagnostics without Qt, network or a full docking
run. It is not a substitute for the development-tree tests.

## Validation evidence

| Question | Evidence |
|---|---|
| Does preparation reproduce the 1IEP upstream artifacts? | `validation/manifest.json`, `tests/` in the development tree |
| Does the committed 1IEP control redock? | `docs/ACADEMIC_VALIDATION.md`, `validation/benchmark/records/` |
| Are the open-target and PoseBusters limits recorded? | `validation/benchmark/README.md` and its records |
| Is the API usable without the desktop shell? | `validation/ci/smoke.py` and the API integration tests in the development tree |

The validation records state their own limits. The project does not claim
PDBBind/CASF performance, enrichment, experimental binding free energies or
general accuracy from these controls.

## Independent reproduction checklist

1. Check out the exact tag or commit named in `BUILD-MANIFEST.json`.
2. Run the development-tree gate above and compare the result with the release
   notes.
3. Run the 1IEP control and compare the top pose and affinity with the recorded
   range.
4. Run at least one system outside the committed examples.
5. Record the OS, Python, Vina version, input hashes and any deviation.
6. Submit a **Reproduction report** issue when the result differs from the recorded
   one; the template asks for the tag, manifest commit, command and sanitized logs.

The project currently has a single maintainer and no third-party reproduction
record. That is a limitation of the evidence, not a hidden claim of correctness;
please report a failed reproduction with the exact command and environment.
