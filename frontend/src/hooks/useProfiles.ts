/* ================================================================
   useProfiles — Save / load named pipeline configuration profiles
   ================================================================ */

import { useState, useCallback, useEffect } from 'react'
import { loadSession, saveSession } from '@/lib/session'

export interface ProfileData {
  [key: string]: string | number | boolean | null | undefined
}

export interface Profile {
  name: string
  createdAt: number
  data: ProfileData
}

const PROFILES_KEY = 'helix:config-profiles'

function loadProfiles(): Profile[] {
  return loadSession<Profile[]>(PROFILES_KEY) ?? []
}

function persistProfiles(profiles: Profile[]) {
  saveSession(PROFILES_KEY, profiles)
}

export function useProfiles() {
  const [profiles, setProfiles] = useState<Profile[]>(loadProfiles)

  useEffect(() => { persistProfiles(profiles) }, [profiles])

  const save = useCallback((name: string, data: ProfileData) => {
    setProfiles((prev) => {
      const filtered = prev.filter((p) => p.name !== name)
      return [{ name, createdAt: Date.now(), data }, ...filtered].slice(0, 20)
    })
  }, [])

  const load = useCallback((name: string): ProfileData | null => {
    const found = profiles.find((p) => p.name === name)
    return found?.data ?? null
  }, [profiles])

  const remove = useCallback((name: string) => {
    setProfiles((prev) => prev.filter((p) => p.name !== name))
  }, [])

  return { profiles, save, load, remove }
}
