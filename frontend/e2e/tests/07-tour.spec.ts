/* ================================================================
   E2E 07 — Guided Tour
   Verifies the spotlight tour overlay appears and can be navigated.
   ================================================================ */

import { test, expect } from '../fixtures'

test.describe('Guided Tour', () => {
  test.beforeEach(async ({ page }) => {
    // Clear the tour-done flag so it auto-shows
    await page.evaluate(() => localStorage.removeItem('helix:tour-done'))
    await page.reload()
    await page.waitForSelector('[data-tour="titlebar-logo"]', { timeout: 30_000 })
  })

  test('tour auto-shows on first run', async ({ page }) => {
    // The overlay mask should appear
    await expect(page.getByText('Welcome to Helix Core')).toBeVisible({ timeout: 10_000 })
  })

  test('tour shows spotlight and tooltip', async ({ page }) => {
    await expect(page.getByText('Welcome to Helix Core')).toBeVisible({ timeout: 10_000 })
    // Next button should be present
    await expect(page.getByRole('button', { name: /Next/ })).toBeVisible()
    // Skip button should be present
    await expect(page.getByText('Skip Tour')).toBeVisible()
  })

  test('next button advances the tour', async ({ page }) => {
    await expect(page.getByText('Welcome to Helix Core')).toBeVisible({ timeout: 10_000 })

    // Click Next
    await page.getByRole('button', { name: /Next/ }).first().click()
    await page.waitForTimeout(500)
    // Second step: System Dashboard
    await expect(page.getByText('System Dashboard')).toBeVisible()
  })

  test('skip button closes the tour', async ({ page }) => {
    await expect(page.getByText('Welcome to Helix Core')).toBeVisible({ timeout: 10_000 })
    await page.getByText('Skip Tour').click()
    await page.waitForTimeout(500)
    // Tour should be gone
    await expect(page.getByText('Welcome to Helix Core')).not.toBeVisible()
  })

  test('tour button in sidebar re-opens tour', async ({ page }) => {
    // First skip the auto-tour
    await expect(page.getByText('Welcome to Helix Core')).toBeVisible({ timeout: 10_000 })
    await page.getByText('Skip Tour').click()
    await page.waitForTimeout(500)

    // Click the Tour Guide button in sidebar
    const tourBtn = page.locator('[data-tour="tour-btn"]')
    await tourBtn.click()
    await expect(page.getByText('Welcome to Helix Core')).toBeVisible({ timeout: 5_000 })
  })

  test('completing all steps sets localStorage flag', async ({ page }) => {
    await expect(page.getByText('Welcome to Helix Core')).toBeVisible({ timeout: 10_000 })

    // Click through all 8 steps
    for (let i = 0; i < 7; i++) {
      await page.getByRole('button', { name: /Next/ }).first().click()
      await page.waitForTimeout(400)
    }
    // Last step — click Finish
    await page.getByRole('button', { name: /Finish/ }).first().click()
    await page.waitForTimeout(500)

    // Tour should be closed and flag set
    const flag = await page.evaluate(() => localStorage.getItem('helix:tour-done'))
    expect(flag).toBe('1')
  })
})
