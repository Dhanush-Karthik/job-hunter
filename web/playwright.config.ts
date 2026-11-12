import { defineConfig, devices } from '@playwright/test'
import { mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'

const real = process.env.JOBHUNTER_E2E_REAL === '1'
const root = path.resolve(import.meta.dirname, '..')
// Inherited by globalSetup and the server; every real-suite invocation owns a fresh database.
if (real && !process.env.JOBHUNTER_E2E_DATA) {
  process.env.JOBHUNTER_E2E_DATA = mkdtempSync(path.join(tmpdir(), 'jobhunter-e2e-'))
}

export default defineConfig({
  testDir: './e2e',
  fullyParallel: !real,
  workers: real ? 1 : undefined,
  retries: 0,
  reporter: 'list',
  outputDir: './e2e/test-results',
  globalSetup: real ? './e2e/real/global-setup.ts' : undefined,
  use: {
    baseURL: real ? 'http://127.0.0.1:8799' : 'http://localhost:5174',
    trace: 'retain-on-failure',
  },
  projects: [{
    name: real ? 'real' : 'chromium',
    testMatch: real ? '**/real/*.spec.ts' : undefined,
    testIgnore: real ? undefined : '**/real/**',
    use: { ...devices['Desktop Chrome'], viewport: { width: 1280, height: 800 } },
  }],
  webServer: real ? {
    command: 'uv run python ../tests/fakes/serve.py',
    url: 'http://127.0.0.1:8799/api/health',
    reuseExistingServer: false,
    env: {
      JOBHUNTER_DATA: process.env.JOBHUNTER_E2E_DATA!,
      JOBHUNTER_NO_SCHEDULER: '1',
      JOBHUNTER_CLAUDE_BIN: path.join(root, 'tests/fakes/claude'),
      JOBHUNTER_NODE_BIN: path.join(root, 'tests/fakes/node'),
      JOBHUNTER_FAKE_SCENARIO: 'happy',
    },
  } : {
    command: 'npm run dev:mock -- --port 5174 --strictPort',
    url: 'http://localhost:5174',
    reuseExistingServer: false,
  },
})
