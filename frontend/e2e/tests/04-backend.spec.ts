/* ================================================================
   E2E 04 — Backend Integration
   Checks the backend comes online and system stats populate.
   ================================================================ */

import { test, expect } from '../fixtures'

test.describe('Backend Integration', () => {
  test('backend comes online', async ({ page }) => {
    // Status pill should eventually show ONLINE
    const pill = page.locator('[data-tour="status-pill"]')
    await expect(pill.getByText('ONLINE')).toBeVisible({ timeout: 30_000 })
  })

  test('system stats populate in dashboard', async ({ page }) => {
    await page.locator('[data-tour="sidebar-nav"]').getByRole('link', { name: 'Dashboard' }).click()
    const grid = page.locator('[data-tour="stats-grid"]')
    // Wait for CPU to show a percentage value (not just "—")
    await expect(grid.getByText(/%/).first()).toBeVisible({ timeout: 15_000 })
  })

  test('statusbar shows CPU and RAM', async ({ page }) => {
    // Wait for stats to load
    await expect(page.getByText(/CPU \d+/)).toBeVisible({ timeout: 15_000 })
    await expect(page.getByText(/RAM \d+/)).toBeVisible()
  })

  test('PDB Fetch page loads form', async ({ page }) => {
    await page.locator('[data-tour="sidebar-nav"]').getByRole('link', { name: 'PDB Fetch' }).click()
    await expect(page.getByPlaceholder('e.g. 1AKE')).toBeVisible()
    await expect(page.getByText('Fetch PDB').last()).toBeVisible()
  })

  test('Docking page loads form', async ({ page }) => {
    await page.locator('[data-tour="sidebar-nav"]').getByRole('link', { name: 'Docking' }).click()
    await expect(page.getByRole('heading', { name: /Molecular Docking/ })).toBeVisible()
  })

  test('Oracle AI page loads form', async ({ page }) => {
    await page.locator('[data-tour="sidebar-nav"]').getByRole('link', { name: 'Oracle AI' }).click()
    await expect(page.getByRole('heading', { name: /Oracle AI/ })).toBeVisible()
  })
})
