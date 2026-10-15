# Releasing VinaStudio

This repository is the release channel: it holds the published source tree and
the artifacts of every version. Releases are cut from a tag and built by CI.

## The two rules that are easy to get wrong

- **The version is the next one in sequence** after the latest release. A release
  number describes *the release*, not the amount of work inside it — never skip a
  number, and never renumber to match an internal milestone.
- **Release notes are written by a human** in [`CHANGELOG.md`](CHANGELOG.md).
  The release body is extracted from that file; nothing is generated from commit
  titles. Keep entries about the product (what a user can now do, what changed,
  what was fixed) — not about the process.

## Steps

### 1. Look at what is already published

```bash
gh release list
```

That listing is what the new version is measured against. Then set the version —
one script keeps every file in step (`pyproject.toml`, the package, the frontend,
the Debian control file, `uv.lock`):

```bash
python packaging/ci/bump-version.py --version 0.4.0
```

### 2. Write the changelog section

Move the entries under `## [Unreleased]` into a new `## [0.4.0] - YYYY-MM-DD`
section (Keep a Changelog's flow), leaving `[Unreleased]` empty behind them, and
add anything the section is still missing. Use the usual
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) headings: `Added`,
`Changed`, `Fixed`, and an explicit `Out of scope` when something was
deliberately left out. Both languages are welcome; the project ships Chinese and
English interfaces.

### 3. Run the pre-flight

```bash
python packaging/ci/release-preflight.py
```

It lists the published releases, then checks the version sequence, the changelog
section, the public wording, the tracked tree, the release metadata, the commit
identity, the workflow, and the open security alerts. Fix everything it reports —
**do not tag** while it fails.

### 4. Build before tagging

Push the branch and trigger the workflow manually. The release job only runs for
tags, so this publishes nothing:

```bash
git push origin main
gh workflow run release.yml
```

Wait for the build to go green. This is the cheapest place to discover a broken
build.

### 5. Tag and push

An annotated tag, so the tag carries an author and a message:

```bash
git tag -a v0.4.0 -m "VinaStudio 0.4.0"
git push origin v0.4.0
```

### 6. Verify what was published

- The release body is the changelog section (not a bare compare link).
- The assets carry the new version number.
- The `preflight` and `build-linux` jobs are green.

## Security alerts

The repository is scanned by Dependabot and CodeQL. The pre-flight refuses to
release while a high or critical alert is open, and "handle it" means one of two
things — never switching the scanner off:

- **Fix it.** CodeQL re-scans on push, so a fix is confirmed by the next run and
  the alert closes itself.
- **Dismiss it with a reason.** The reason is the audit trail: the Security tab
  keeps the alert, the dismissal and the argument, so the next reader sees why it
  is not a bug instead of a bare number. `.github/codeql/codeql-config.yml`
  documents the triage of the `py/path-injection` family — the desktop UI hands
  the backend absolute paths the user picked in a file dialog, which is the API's
  contract, and containment where it is required goes through
  `core/paths.resolve_within`.

The configuration is `.github/codeql/codeql-config.yml` (advanced setup);
`workflow_dispatch` on the CodeQL workflow re-scans on demand.

Every push to `main` triggers a scan, so a release can inherit alerts that did not
exist at the last one: the interactive-operations work added five (2026-10-15 —
one critical `py/command-line-injection`, three `py/path-injection`, one
`py/stack-trace-exposure`), each triaged by hand. The critical one was a genuine
false positive: `subprocess.run()` gets an argv list with no `shell=True`, so a
path containing metacharacters is only a filename. Look at the Security tab, or
run `gh api repos/hubehero/VinaStudio/code-scanning/alerts?state=open`, *before*
starting a release rather than during it.

The same goes for `engine-check.yml`: check that both its jobs are green. The
Windows one is the evidence behind any Windows claim — it docks the 1iep gold
standard through the command-line backend and asserts the same regime the Linux
tests use (2026-10-15: 23.1 s, best affinity −13.239 kcal/mol on Windows against
−13.228 on Linux).

Release artifacts are **Linux only**. `windows-build.yml` builds the Windows
installer and publishes nothing — that stays true until somebody has installed it on
a real machine and walked through the application, which is the last unverified link
on that platform. It is ready to test: the bundle builds, the engine inside it runs
on Windows, and the installer compiles (219 MB, 2026-10-15).

## What CI does

On `v*` tags, `.github/workflows/release.yml` runs three jobs:

| Job | Purpose |
|---|---|
| `preflight` | the same checks as step 3 (in `--allow-published` mode, since the tag already exists) |
| `build-linux` | frontend build, PyInstaller bundle, `.deb` and tarball |
| `create-release` | creates the GitHub Release with the body taken from `CHANGELOG.md` |

A failing `preflight` stops the chain: a release that breaks the rules above
cannot be published.

## Artifacts

| Asset | Target |
|---|---|
| `vinastudio_X.Y.Z_amd64.deb` | Ubuntu / Debian (amd64) |
| `vinastudio-X.Y.Z-linux-amd64.tar.gz` | portable — unpack and run `vinastudio/vinastudio` |

Requires an OpenGL desktop session. The scientific stack (vina, meeko, RDKit) is
bundled. Windows is not released: upstream `vina` has no Windows wheels.
