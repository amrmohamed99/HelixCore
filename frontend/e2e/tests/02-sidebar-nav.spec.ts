/* ================================================================
   E2E 02 — Sidebar Navigation
   Clicks every sidebar link and verifies the correct page loads.
   ================================================================ */

import { test, expect } from '../fixtures'

const ROUTES = [
  { label: 'Dashboard', heading: 'Mission Control' },
  { label: 'PDB Fetch', heading: 'PDB Fetch' },
  { label: 'Pocket Analysis', heading: 'Pocket Analysis' },
  { label: 'Batch Generate', heading: 'Batch Generate' },
  { label: 'Minimization', heading: 'Minimization' },
  { label: 'Format Convert', heading: 'Format Convert' },
  { label: 'Auto Pipeline', heading: 'Auto Pipeline' },
  { label: 'Docking', heading: 'Molecular Docking' },
  { label: 'Similarity', heading: 'Similarity Search' },
  { label: 'Oracle AI', heading: 'Oracle AI' },
  { label: 'Results', heading: 'Results Explorer' },
  { label: 'About', heading: 'Amr Mohamed' },
]

test.describe('Sidebar Navigation', () => {
  for (const route of ROUTES) {
    test(`navigates to ${route.label}`, async ({ page }) => {
      const link = page.locator('[data-tour="sidebar-nav"]').getByRole('link', { name: route.label })
      await link.click()
      await expect(page.getByText(route.heading).first()).toBeVisible({ timeout: 5_000 })
    })
  }

  test('category headers are visible', async ({ page }) => {
    for (const cat of ['OVERVIEW', 'PREPARATION', 'PROCESSING', 'SCREENING', 'OUTPUT', 'SYSTEM']) {
      await expect(page.getByText(cat, { exact: true })).toBeVisible()
    }
  })
})
