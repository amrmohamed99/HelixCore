/* ================================================================
   Electron Test Fixtures — launch Helix Core for E2E testing
   Worker-scoped: ONE Electron app per worker (= 1 for serial).
   Each test gets a `page` pointing at the main renderer window.
   ================================================================ */

import { test as base, type Page } from '@playwright/test'
import { _electron as electron, type ElectronApplication } from 'playwright'
import path from 'path'
import fs from 'fs'

/** Absolute path to the built Electron main entry */
const MAIN_JS = path.resolve(__dirname, '..', 'dist-electron', 'main.js')
const TEST_RESULTS_DIR = path.resolve(__dirname, '..', 'test-results')
const E2E_USER_DATA_DIR = path.join(TEST_RESULTS_DIR, 'electron-user-data')
const PACKAGED_EXECUTABLE = process.env.HELIX_E2E_EXECUTABLE
  ? path.resolve(process.env.HELIX_E2E_EXECUTABLE)
  : null

/**
 * Find the main BrowserWindow (not the splash).
 * The main window loads index.html which contains the React app.
 * The splash window loads splash.html.
 */
async function getMainWindow(app: ElectronApplication, timeout = 45_000): Promise<Page> {
  const deadline = Date.now() + timeout

  while (Date.now() < deadline) {
    const windows = app.windows()
    for (const win of windows) {
      const url = win.url()
      // Main window loads index.html (production) or localhost (dev)
      if (url.includes('index.html') || url.includes('localhost')) {
        // Wait for React to hydrate
        try {
          await win.waitForSelector('[data-tour="titlebar-logo"]', { timeout: 15_000 })
          return win
        } catch {
          // Not ready yet, keep trying
        }
      }
    }
    await new Promise((r) => setTimeout(r, 1000))
  }

  // Fallback: return whatever window we have
  const windows = app.windows()
  if (windows.length > 0) return windows[windows.length - 1]
  throw new Error('No Electron windows found within timeout')
}

/**
 * Extended Playwright fixtures with worker-scoped Electron app.
 * The app launches ONCE and is shared across all tests in the worker.
 */
export const test = base.extend<
  { page: Page },
  { electronApp: ElectronApplication; mainPage: Page }
>({
  /* Worker-scoped: app launches once for all tests */
  electronApp: [
    async ({}, use) => {
      /* Keep Chromium cache/localStorage out of the user's real Electron
         profile. This is also required in restricted runners where APPDATA is
         readable but not writable. Resolve and validate the deletion target
         before cleaning it so teardown can never escape test-results/. */
      const resolvedUserData = path.resolve(E2E_USER_DATA_DIR)
      if (!resolvedUserData.startsWith(`${TEST_RESULTS_DIR}${path.sep}`)) {
        throw new Error(`Unsafe E2E user-data path: ${resolvedUserData}`)
      }
      fs.rmSync(resolvedUserData, { recursive: true, force: true })
      fs.mkdirSync(resolvedUserData, { recursive: true })

      if (PACKAGED_EXECUTABLE && !fs.existsSync(PACKAGED_EXECUTABLE)) {
        throw new Error(`HELIX_E2E_EXECUTABLE does not exist: ${PACKAGED_EXECUTABLE}`)
      }

      const commonArgs = [
          `--user-data-dir=${resolvedUserData}`,
          '--disable-gpu',
          /* Restricted Windows runners can deny Chromium child sandboxes
             access to the workspace-hosted Electron distribution and local
             file:// renderer. This affects only the automated test process;
             production BrowserWindows retain sandbox: true. */
          '--no-sandbox',
      ]

      const app = await electron.launch({
        ...(PACKAGED_EXECUTABLE
          ? { executablePath: PACKAGED_EXECUTABLE, args: commonArgs }
          : { args: [...commonArgs, MAIN_JS] }),
        env: {
          ...process.env,
          NODE_ENV: 'production',
          HELIX_E2E_TESTING: '1',
        },
        // A first launch after npm ci can spend tens of seconds initializing
        // Chromium/Electron caches on Windows CI. Keep this above the normal
        // Playwright test timeout so a healthy cold start is not misreported.
        timeout: 60_000,
      })
      await use(app)
      // Bounded graceful teardown. A forced taskkill of the Electron parent can
      // surface Windows' 0x80000003 breakpoint dialog even when the test itself
      // is healthy. The app's before-quit handler terminates the backend child.
      const electronProcess = app.process()
      const processExited = new Promise<void>((resolve) => {
        if (electronProcess.exitCode !== null || electronProcess.signalCode !== null) {
          resolve()
        } else {
          electronProcess.once('exit', () => resolve())
        }
      })
      let closedGracefully = false
      const closeAttempt = app.close()
        .then(() => { closedGracefully = true })
        .catch(() => { /* The process-level fallback handles this below. */ })

      await Promise.race([
        closeAttempt,
        new Promise<void>((resolve) => setTimeout(resolve, 8_000)),
      ])

      // If Electron did not exit within the grace window, terminate only the
      // Playwright child process; do not invoke taskkill /T on the GUI parent.
      // Then wait briefly for the transport to observe the exit so an unresolved
      // close operation cannot hold the Playwright worker open for 60 seconds.
      try {
        if (!closedGracefully && electronProcess.exitCode === null) {
          electronProcess.kill()
        }
      } catch {
        // Already gone.
      }
      await Promise.race([
        closeAttempt,
        processExited,
        new Promise<void>((resolve) => setTimeout(resolve, 5_000)),
      ])
    },
    { scope: 'worker' },
  ],

  /* Worker-scoped: find the main renderer window once */
  mainPage: [
    async ({ electronApp }, use) => {
      const page = await getMainWindow(electronApp)
      await use(page)
    },
    { scope: 'worker' },
  ],

  /* Test-scoped: each test gets the same page, navigated to Dashboard */
  page: async ({ mainPage }, use) => {
    /* Exercise the real dismissal controls so React state and localStorage stay
       synchronized. Removing overlay DOM directly leaves the component mounted
       and allows it to intercept later navigation after a re-render. */
    // GuidedTour is mounted later in Layout and therefore sits above the
    // onboarding dialog; dismiss it first so it cannot intercept the click.
    const tourSkip = mainPage.getByRole('button', { name: 'Skip tour' })
    if (await tourSkip.isVisible().catch(() => false)) {
      await tourSkip.click()
    }
    const onboardingSkip = mainPage.getByRole('button', { name: 'Skip intro' })
    if (await onboardingSkip.isVisible().catch(() => false)) {
      await onboardingSkip.click()
    }

    await mainPage.evaluate(() => {
      window.location.hash = '#/dashboard'
    })
    await mainPage
      .getByRole('heading', { name: /Mission Control/ })
      .first()
      .waitFor({ state: 'visible', timeout: 10_000 })
    await use(mainPage)
  },
})

export { expect } from '@playwright/test'
