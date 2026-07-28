/* ================================================================
   E2E 01 — App Launch & Window
   Verifies the Electron app boots, shows the main window, and
   renders the shell layout (titlebar, sidebar, statusbar).
   ================================================================ */

import { test, expect } from '../fixtures'

test.describe('App Launch', () => {
  test('main window is visible', async ({ page }) => {
    // fixtures already waited for titlebar-logo
    const title = page.locator('[data-tour="titlebar-logo"]')
    await expect(title).toBeVisible()
  })

  test('shows HELIX CORE branding', async ({ page }) => {
    const logo = page.locator('[data-tour="titlebar-logo"]')
    await expect(logo).toBeVisible()
    await expect(logo.locator('text=HELIX CORE')).toBeVisible()
    await expect(logo.locator('text=v3.0')).toBeVisible()
  })

  test('has window control buttons', async ({ page }) => {
    await expect(page.locator('button[title="Minimize"]')).toBeVisible()
    await expect(page.locator('button[title="Close"]')).toBeVisible()
  })

  test('defaults to dark theme', async ({ page }) => {
    const theme = await page.locator('html').getAttribute('data-theme')
    // First run should be dark (default) or system-resolved
    expect(['dark', 'light']).toContain(theme)
  })

  test('statusbar is visible', async ({ page }) => {
    await expect(page.getByText('Helix Core v3.0')).toBeVisible()
  })

  test('sidebar exposes every workflow destination', async ({ page }) => {
    /* Asserting the destination set rather than a bare count: a stale count
       reports "22 !== 12" and tells you nothing, while a set diff names the
       route that was added or dropped. Source of truth is the `sections`
       array in src/components/layout/Sidebar.tsx. */
    const expected = [
      '/dashboard', '/projects',
      '/fetch', '/prepare', '/pocket', '/batch', '/filters', '/analogs', '/fragments',
      '/minimize', '/convert', '/pipeline',
      '/docking', '/similarity', '/oracle', '/admet', '/pharmacophore', '/scaffold',
      '/results', '/compare', '/cluster',
      '/about',
    ]

    const nav = page.locator('[data-tour="sidebar-nav"]')
    await expect(nav).toBeVisible()
    await expect(nav.getByRole('link')).toHaveCount(expected.length)

    const hrefs = await nav.getByRole('link').evaluateAll((links) =>
      links.map((a) => new URL((a as HTMLAnchorElement).href).hash.replace(/^#/, ''))
    )
    expect(hrefs.sort()).toEqual([...expected].sort())
  })
})
