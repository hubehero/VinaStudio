import { defineConfig } from '@playwright/test'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const baseURL = process.env.E2E_BASE_URL ?? 'http://127.0.0.1:8760'

export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  reporter: process.env.CI ? [['line'], ['junit', { outputFile: 'test-results/e2e.xml' }]] : 'list',
  use: {
    baseURL,
    headless: true,
    trace: 'retain-on-failure',
  },
  webServer: process.env.E2E_BASE_URL
    ? undefined
    : {
        command:
          'pnpm -C web build && uv run python scripts/build_web.py && ' +
          'VINASTUDIO_HOME=$(mktemp -d) uv run uvicorn ' +
          'vinastudio.server.app:create_app --factory --host 127.0.0.1 --port 8760 --log-level warning',
        cwd: root,
        url: baseURL,
        timeout: 180_000,
        reuseExistingServer: false,
      },
})
