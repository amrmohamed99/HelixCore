/* ================================================================
   Session Storage — persist and restore app state across restarts
   ================================================================ */

const PREFIX = 'helix:'

/** Type-safe read from localStorage */
export function loadSession<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(`${PREFIX}${key}`)
    return raw ? (JSON.parse(raw) as T) : fallback
  } catch {
    return fallback
  }
}

/** Type-safe write to localStorage */
export function saveSession<T>(key: string, value: T): void {
  try {
    localStorage.setItem(`${PREFIX}${key}`, JSON.stringify(value))
  } catch {
    /* quota exceeded — silently ignore */
  }
}

/** Remove a specific key */
export function clearSession(key: string): void {
  localStorage.removeItem(`${PREFIX}${key}`)
}

/* ---- Convenience keys ---- */

export const SESSION_KEYS = {
  pipelineSteps: 'pipeline-steps',
  recentPaths: 'recent-paths',
  sidebarCollapsed: 'sidebar-collapsed',
  dockOpen: 'dock-open',
} as const

/* ---- Recent paths helper ---- */

const MAX_RECENT = 5

export function getRecentPaths(fieldKey: string): string[] {
  const all = loadSession<Record<string, string[]>>(SESSION_KEYS.recentPaths, {})
  return all[fieldKey] ?? []
}

export function addRecentPath(fieldKey: string, path: string): void {
  const all = loadSession<Record<string, string[]>>(SESSION_KEYS.recentPaths, {})
  const existing = all[fieldKey] ?? []
  const updated = [path, ...existing.filter((p) => p !== path)].slice(0, MAX_RECENT)
  all[fieldKey] = updated
  saveSession(SESSION_KEYS.recentPaths, all)
}
