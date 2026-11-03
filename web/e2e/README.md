# Browser smoke

Requires Playwright's Chromium:

```bash
pnpm -C web install
pnpm -C web exec playwright install chromium
pnpm -C web e2e
```

The config starts a production FastAPI server on an isolated `VINASTUDIO_HOME`;
the test initialises a temporary workspace through the API. It is a route and
diagnostics smoke, not a substitute for the pytest 1IEP pipeline or the
manual interaction record.
