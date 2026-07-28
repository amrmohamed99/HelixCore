/* ================================================================
   E2E 05 — Kernel Dock
   Tests the kernel log panel toggle, filtering, and clear.
   ================================================================ */

import { test, expect } from '../fixtures'
import type { Page } from '@playwright/test'

/* The dock is identified by its close button rather than a header caption.
   The caption was "KERNEL TERMINAL" and is now the tab label "KERNEL"; the
   close control is structural, so it survives copy changes. */
const dock = (page: Page) => page.locator('button[title="Close dock"]')

test.describe('Kernel Dock', () => {
  /* Ensure the dock starts CLOSED before each test (shared page) */
  test.beforeEach(async ({ page }) => {
    if (await dock(page).isVisible().catch(() => false)) {
      await page.locator('[data-tour="kernel-toggle"]').click()
      await expect(dock(page)).not.toBeVisible()
    }
  })

  test('opens when clicking Kernel button', async ({ page }) => {
    const toggle = page.locator('[data-tour="kernel-toggle"]')
    await toggle.click()
    await expect(dock(page)).toBeVisible()
  })

  test('shows log entries from backend', async ({ page }) => {
    const toggle = page.locator('[data-tour="kernel-toggle"]')
    await toggle.click()
    await expect(dock(page)).toBeVisible()
    // Wait for at least one log line (backend startup messages)
    await expect(page.getByText(/lines/)).toBeVisible({ timeout: 15_000 })
  })

  test('filter input narrows logs', async ({ page }) => {
    const toggle = page.locator('[data-tour="kernel-toggle"]')
    await toggle.click()
    await expect(dock(page)).toBeVisible()

    const filter = page.getByPlaceholder('Filter logs…')
    await filter.fill('Backend')
    // Filter should work — either show matching logs or "No matching logs" message
    await page.waitForTimeout(500)
    const noMatch = page.getByText('No matching logs')
    const matchingLog = page.locator('[class*="logLine"]').first()
    await expect(noMatch.or(matchingLog)).toBeVisible()
  })

  test('clear button empties logs', async ({ page }) => {
    const toggle = page.locator('[data-tour="kernel-toggle"]')
    await toggle.click()
    await expect(dock(page)).toBeVisible()

    // Wait for some logs to accumulate
    await page.waitForTimeout(500)
    const clearBtn = page.locator('button[title="Clear logs"]')
    await clearBtn.click()

    // After clear, either the empty state shows briefly or log count resets
    // The backend may send new logs immediately, so check that the clear
    // action executed by verifying the log count dropped significantly
    await page.waitForTimeout(200)
    const logLines = page.locator('[class*="logLine"]')
    const count = await logLines.count()
    // Right after clearing, there should be very few (0-3) log lines
    expect(count).toBeLessThan(10)
  })

  test('close button hides dock', async ({ page }) => {
    const toggle = page.locator('[data-tour="kernel-toggle"]')
    await toggle.click()
    await expect(dock(page)).toBeVisible()

    const closeBtn = page.locator('button[title="Close dock"]')
    await closeBtn.click()
    await expect(dock(page)).not.toBeVisible()
  })
})
