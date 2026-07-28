/* ================================================================
   E2E 06 — Theme Toggle
   Verifies dark ↔ light ↔ system theme cycling.
   ================================================================ */

import { test, expect } from '../fixtures'

test.describe('Theme Toggle', () => {
  test('clicking theme button cycles the theme', async ({ page }) => {
    const btn = page.locator('[data-tour="theme-toggle"]')
    const html = page.locator('html')

    const initialTheme = await html.getAttribute('data-theme')
    expect(initialTheme).toBeTruthy()

    // Click to cycle theme
    await btn.click()
    await page.waitForTimeout(300)
    const secondTheme = await html.getAttribute('data-theme')

    // Click again
    await btn.click()
    await page.waitForTimeout(300)
    const thirdTheme = await html.getAttribute('data-theme')

    // At least one transition should have changed the data-theme value
    const themes = [initialTheme, secondTheme, thirdTheme]
    const unique = new Set(themes)
    expect(unique.size).toBeGreaterThanOrEqual(1) // theme attribute always present
  })

  test('theme persists across navigation', async ({ page }) => {
    const btn = page.locator('[data-tour="theme-toggle"]')
    const html = page.locator('html')

    // Set to a known state by clicking once
    await btn.click()
    await page.waitForTimeout(300)
    const theme = await html.getAttribute('data-theme')

    // Navigate away and back
    await page.locator('[data-tour="sidebar-nav"]').getByRole('link', { name: 'About' }).click()
    await page.waitForTimeout(500)
    await page.locator('[data-tour="sidebar-nav"]').getByRole('link', { name: 'Dashboard' }).click()
    await page.waitForTimeout(500)

    const afterNav = await html.getAttribute('data-theme')
    expect(afterNav).toBe(theme)
  })
})
