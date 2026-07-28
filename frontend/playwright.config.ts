/* ================================================================
   Playwright E2E Config — Helix Core Electron App
   Uses Playwright's Electron support (_electron) instead of browsers.
   ================================================================ */

import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  expect: { timeout: 10_000 },
  retries: 0,
  workers: 1, // Electron tests must run serially
  fullyParallel: false, // All tests share one worker (= one Electron app)
  reporter: [['html', { open: 'never' }], ['list']],
  use: {
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
})
