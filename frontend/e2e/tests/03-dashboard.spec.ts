/* ================================================================
   E2E 03 — Dashboard
   Verifies the dashboard widgets render correctly.
   ================================================================ */

import { test, expect } from '../fixtures'

test.describe('Dashboard', () => {
  test.beforeEach(async ({ page }) => {
    await page.locator('[data-tour="sidebar-nav"]').getByRole('link', { name: 'Dashboard' }).click()
    await expect(page.getByText('Mission Control')).toBeVisible()
  })

  test('shows stat cards', async ({ page }) => {
    const grid = page.locator('[data-tour="stats-grid"]')
    await expect(grid).toBeVisible()
    await expect(grid.getByText('Backend')).toBeVisible()
    await expect(grid.getByText('CPU Usage')).toBeVisible()
    await expect(grid.getByText('RAM Usage')).toBeVisible()
    await expect(grid.getByText('Pipeline')).toBeVisible()
  })

  test('shows pipeline card', async ({ page }) => {
    const card = page.locator('[data-tour="pipeline-card"]')
    await expect(card).toBeVisible()
    await expect(card.getByText('Virtual Screening Pipeline')).toBeVisible()
  })

  test('pipeline has 8 steps', async ({ page }) => {
    const card = page.locator('[data-tour="pipeline-card"]')
    // Each step has a label like "PDB Fetch", "Pocket Scan", etc.
    for (const step of ['PDB Fetch', 'Pocket Scan', 'Ligand Gen', 'Minimize', 'Convert', 'Docking', 'Oracle AI', 'Results']) {
      await expect(card.getByText(step, { exact: true }).first()).toBeVisible()
    }
  })

  test('shows tool pills', async ({ page }) => {
    const pills = page.locator('[data-tour="tools-pills"]')
    await expect(pills).toBeVisible()
    await expect(pills.getByText('RDKit')).toBeVisible()
  })

  test('has Run Full Pipeline button', async ({ page }) => {
    await expect(page.getByText('Run Full Pipeline →')).toBeVisible()
  })
})
