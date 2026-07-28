/* ================================================================
   ConfigProfiles — Save/load named configuration presets
   ================================================================ */

import { useState } from 'react'
import type { ProfileData } from '@/hooks/useProfiles'
import { useProfiles } from '@/hooks/useProfiles'
import cp from './ConfigProfiles.module.css'

interface ConfigProfilesProps {
  /** Function returning current form state */
  getCurrent: () => ProfileData
  /** Function applying a profile's data to the form */
  applyCurrent: (data: ProfileData) => void
}

export default function ConfigProfiles({ getCurrent, applyCurrent }: ConfigProfilesProps) {
  const { profiles, save, load, remove } = useProfiles()
  const [newName, setNewName] = useState('')
  const [open, setOpen] = useState(false)

  const handleSave = () => {
    const name = newName.trim()
    if (!name) return
    save(name, getCurrent())
    setNewName('')
  }

  const handleLoad = (name: string) => {
    const data = load(name)
    if (data) applyCurrent(data)
    setOpen(false)
  }

  return (
    <div className={cp.wrapper}>
      <button className={cp.toggle} onClick={() => setOpen(!open)} title="Configuration profiles">
        ⚙️ Profiles {profiles.length > 0 && <span className={cp.count}>{profiles.length}</span>}
      </button>

      {open && (
        <div className={cp.dropdown}>
          <div className={cp.saveRow}>
            <input
              className={cp.input}
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="Profile name…"
              onKeyDown={(e) => e.key === 'Enter' && handleSave()}
            />
            <button className={cp.saveBtn} onClick={handleSave} disabled={!newName.trim()}>
              💾
            </button>
          </div>

          {profiles.length === 0 ? (
            <div className={cp.empty}>No saved profiles</div>
          ) : (
            <ul className={cp.list}>
              {profiles.map((p) => (
                <li key={p.name} className={cp.item}>
                  <button className={cp.loadBtn} onClick={() => handleLoad(p.name)}>
                    {p.name}
                    <span className={cp.date}>
                      {new Date(p.createdAt).toLocaleDateString()}
                    </span>
                  </button>
                  <button className={cp.deleteBtn} onClick={() => remove(p.name)} title="Delete" aria-label="Delete profile">
                    ✕
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}
