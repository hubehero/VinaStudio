## What changed

<!-- One or two sentences. Link the issue if there is one. -->

## Why

<!-- The problem this solves, and any trade-off the reviewer should know about. -->

## Checks

- [ ] Tests pass (`uv run pytest -q`)
- [ ] Lint and types pass (`uv run ruff check .`, `pnpm -C web typecheck`)
- [ ] User-facing text is updated in both languages (`zh-CN` and `en-US` locales)
- [ ] Documentation is updated in both languages when behaviour changed
      (`README.md` / `README.en.md`, `docs/*.md` / `docs/*.zh-CN.md`)
- [ ] No personal paths, email addresses, tokens or private sample data in the diff
- [ ] For interface changes: screenshots in light and dark themes

## Notes for the reviewer

<!-- Optional: what you are unsure about, or what you deliberately did not change. -->
