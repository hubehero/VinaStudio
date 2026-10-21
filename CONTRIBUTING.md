# Contributing to VinaStudio

**English** · [简体中文](CONTRIBUTING.zh-CN.md)

Thanks for taking the time to contribute. VinaStudio is a small project, so the
most useful contributions are reproducible bug reports, focused fixes and
documentation improvements. You do not need to be a docking expert to help.

## Where the project lives

This repository is the **release channel**: it carries the application source,
the packaging and the public documentation. The development tree, which also
contains the test suite, fixtures and the hot-reload workflow, is maintained
alongside it. That is why you will not find `tests/` here.

If your change needs a test, include it in the pull request; the maintainer runs
the full suite in the development tree before merging. For anything larger than a
one-line fix, open an issue first so we can agree on the approach.

## Reporting a bug

A report that can be reproduced is worth more than a long description. Please
include:

1. the VinaStudio version (shown in the status bar and on the About page);
2. the operating system and version;
3. the renderer string from **Environment → Actual renderer**;
4. the steps that lead to the problem;
5. what you expected and what happened;
6. the relevant part of `~/.vinastudio/logs/vinastudio.log`
   (`%USERPROFILE%\.vinastudio\logs\vinastudio.log` on Windows), with any
   personal paths removed.

If the problem involves a structure, a minimal input file helps enormously. Do
not upload a file you are not allowed to share.

## Feature requests

Open an issue and describe the problem you are trying to solve, not only the
solution you have in mind. A concrete workflow — “I want to compare ten ligands
against the same receptor and export one table” — is easier to act on than an
abstract feature name.

## Pull requests

1. Fork the repository and create a branch from `main`.
2. Keep the change focused; separate unrelated fixes.
3. Follow the existing code style and the notes below.
4. Update the documentation when behaviour changes. User-facing changes belong in
   `CHANGELOG.md` under `[Unreleased]`.
5. Open the pull request with a short description of the problem and the fix.
6. Make sure the checks you can run locally pass.

Review looks at correctness first, then at whether the change fits the project's
scientific conventions. A smaller, clearer patch is easier to merge than a broad
rewrite.

## Development setup

The public tree can build the application:

```bash
git clone https://github.com/<your-username>/VinaStudio.git
cd VinaStudio

uv sync --extra dev
pnpm -C web install
pnpm -C web build
```

Run the checks that exist here:

```bash
uv run ruff check .
pnpm -C web typecheck
pnpm -C web build:checked
```

Do not run `uv run` inside a release checkout while preparing a release: it
re-resolves the environment and can rewrite `uv.lock` with a local package
mirror. Use the interpreter directly for release scripts.

## Code style

### Python

- Target Python 3.12; use type hints where they clarify the contract.
- Keep `vinastudio/core/` free of Qt and FastAPI. It must stay testable without a
  display.
- Raise domain errors from `vinastudio.core.errors`; the API maps them centrally.
- Comments explain *why*, not *what*.

### TypeScript and Vue

- Vue 3 with `<script setup>` and the Composition API.
- Keep contract types in `web/src/types/api.ts`.
- Run `pnpm -C web typecheck`; a production build strips types without checking
  them.

### Documentation

- User-facing documents come in English (`NAME.md`) and Simplified Chinese
  (`NAME.zh-CN.md`), with a language link at the top of each pair.
- Keep the README's documentation table up to date when adding a page.
- Do not put internal task numbers or process notes into public documents.

## Commit messages

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add SMILES input support
fix: correct the ligand type for a one-residue peptide
docs: explain the Windows antialiasing default
```

A commit should describe one change. If the explanation needs a paragraph, put it
in the body rather than in the subject.

## Translations

The application ships Chinese and English interfaces, and the main documents have
both languages. If you change a user-visible string, update both locales:
`web/src/i18n/locales/zh-CN.ts` and `en-US.ts`. If you change a document, update
its pair as well, or note in the pull request that the translation is pending.

## Code of conduct

Participation is covered by [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md). Be
respectful; technical disagreement is welcome, personal attacks are not.

## Security

Please do not report vulnerabilities in a public issue. Follow
[SECURITY.md](SECURITY.md) instead.

## License

By contributing, you agree that your contributions are licensed under the MIT
License, the same terms as the project.
