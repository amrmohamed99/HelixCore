/* ================================================================
   StructureViewer — Interactive 3D molecular structure viewer
   Uses Mol* (Molstar) for rendering PDB/PDBQT/MOL2 files.
   Supports inline mini-viewer and expandable full-screen mode.
   ================================================================ */

import { useEffect, useRef, useState, useCallback } from 'react'
import css from './StructureViewer.module.css'

const BASE_URL = 'http://127.0.0.1:8299'

type RepresentationType = 'cartoon' | 'ball-and-stick' | 'spacefill' | 'surface'

interface StructureViewerProps {
  /** Absolute path to a structure file (.pdb, .pdbqt, .mol2, .sdf, .cif) */
  filePath?: string
  /** Alternatively, raw structure data as a string */
  data?: string
  /** Format of the data (auto-detected from filePath extension when omitted) */
  format?: 'pdb' | 'pdbqt' | 'mol2' | 'sdf' | 'cif' | 'mmcif'
  /** Height of the inline viewer in px */
  height?: number
  /** Optional label displayed at the bottom left */
  label?: string
  /** Whether to show the toolbar (default true) */
  showToolbar?: boolean
  /** Whether to allow full-screen expansion (default true) */
  allowFullscreen?: boolean
  /** Optional second file to overlay (e.g. ligand on receptor) */
  overlayFilePath?: string
  /** Format of the overlay file */
  overlayFormat?: 'pdb' | 'pdbqt' | 'mol2' | 'sdf'
}

/** Map file extension to Mol* BuiltInTrajectoryFormat */
function detectFormat(filePath: string): string {
  const ext = filePath.split('.').pop()?.toLowerCase() ?? ''
  const map: Record<string, string> = {
    pdb: 'pdb',
    pdbqt: 'pdb',
    cif: 'mmcif',
    mcif: 'mmcif',
    mmcif: 'mmcif',
    mol2: 'mol2',
    sdf: 'sdf',
    mol: 'sdf',
  }
  return map[ext] ?? 'pdb'
}

export default function StructureViewer({
  filePath,
  data,
  format,
  height = 320,
  label,
  showToolbar = true,
  allowFullscreen = true,
  overlayFilePath,
  overlayFormat,
}: StructureViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const fullscreenContainerRef = useRef<HTMLDivElement>(null)
  const viewerRef = useRef<any>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [repr, setRepr] = useState<RepresentationType>('cartoon')
  const [showReprMenu, setShowReprMenu] = useState(false)
  const initedRef = useRef(false)

  /** Fetch file content from the backend proxy endpoint */
  const fetchFileContent = useCallback(async (path: string): Promise<string> => {
    const res = await fetch(`${BASE_URL}/api/system/structure-file?path=${encodeURIComponent(path)}`)
    if (!res.ok) throw new Error(`Failed to load structure: ${res.status}`)
    return res.text()
  }, [])

  /** Initialize Mol* viewer */
  const initViewer = useCallback(async (target: HTMLDivElement) => {
    try {
      const { Viewer } = await import('molstar/lib/apps/viewer/app')
      const viewer = await Viewer.create(target, {
        layoutIsExpanded: false,
        layoutShowControls: false,
        layoutShowRemoteState: false,
        layoutShowSequence: false,
        layoutShowLog: false,
        layoutShowLeftPanel: false,
        collapseLeftPanel: true,
        collapseRightPanel: true,
        viewportShowControls: false,
        viewportShowExpand: false,
        viewportShowSettings: false,
        viewportShowSelectionMode: false,
        viewportShowAnimation: false,
        viewportShowTrajectoryControls: false,
      })
      return viewer
    } catch (err) {
      console.error('Failed to initialize Mol* viewer:', err)
      throw err
    }
  }, [])

  /** Load structure data into the viewer */
  const loadStructure = useCallback(async (viewer: any, content: string, fmt: string, overlayContent?: string, overlayFmt?: string) => {
    try {
      /* Clear existing structures */
      viewer.plugin.clear()

      /* Load main structure */
      await viewer.loadStructureFromData(content, fmt as any, { dataLabel: label || 'Structure' })

      /* Load overlay (e.g. ligand) if provided */
      if (overlayContent) {
        await viewer.loadStructureFromData(overlayContent, (overlayFmt || 'pdb') as any, { dataLabel: 'Overlay' })
      }
    } catch (err) {
      console.error('Failed to load structure:', err)
      throw err
    }
  }, [label])

  /** Main effect: initialize viewer and load data */
  useEffect(() => {
    if (initedRef.current) return
    if (!containerRef.current) return
    if (!filePath && !data) return

    initedRef.current = true
    let cancelled = false

    const run = async () => {
      setLoading(true)
      setError(null)

      try {
        const target = containerRef.current!

        /* Resolve data */
        let content: string
        let fmt: string
        if (data) {
          content = data
          fmt = format ?? 'pdb'
        } else {
          content = await fetchFileContent(filePath!)
          fmt = format ?? detectFormat(filePath!)
        }

        if (cancelled) return

        /* Initialize viewer */
        const viewer = await initViewer(target)
        if (cancelled) { viewer.plugin.dispose(); return }
        viewerRef.current = viewer

        /* Load structure */
        let overlayContent: string | undefined
        if (overlayFilePath) {
          overlayContent = await fetchFileContent(overlayFilePath)
        }
        if (cancelled) { viewer.plugin.dispose(); return }

        await loadStructure(viewer, content, fmt, overlayContent, overlayFormat ?? (overlayFilePath ? detectFormat(overlayFilePath) : undefined))
        if (cancelled) return

        setLoading(false)
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load 3D viewer')
          setLoading(false)
        }
      }
    }

    run()
    return () => { cancelled = true }
  }, [filePath, data, format, overlayFilePath, overlayFormat, fetchFileContent, initViewer, loadStructure])

  /** Cleanup on unmount */
  useEffect(() => {
    return () => {
      if (viewerRef.current) {
        try { viewerRef.current.plugin.dispose() } catch { /* ignore */ }
        viewerRef.current = null
      }
      initedRef.current = false
    }
  }, [])

  /** Handle representation change */
  const changeRepresentation = useCallback(async (type: RepresentationType) => {
    setRepr(type)
    setShowReprMenu(false)
    const viewer = viewerRef.current
    if (!viewer) return

    const plugin = viewer.plugin
    const structures = plugin.managers.structure.hierarchy.current.structures
    if (!structures.length) return

    /* Map our simple names to Mol* preset IDs */
    const presetMap: Record<RepresentationType, string> = {
      'cartoon': 'preset-structure-representation-rcsb',
      'ball-and-stick': 'preset-structure-representation-rcsb',
      'spacefill': 'preset-structure-representation-rcsb',
      'surface': 'preset-structure-representation-rcsb',
    }

    try {
      for (const s of structures) {
        const comp = s.components
        for (const c of comp) {
          /* Remove existing representations */
          for (const r of c.representations) {
            await plugin.managers.structure.hierarchy.remove([r])
          }
        }

        /* Apply new representation */
        const reprType = type === 'cartoon' ? 'cartoon'
          : type === 'ball-and-stick' ? 'ball-and-stick'
          : type === 'spacefill' ? 'spacefill'
          : type === 'gaussian-surface' ? 'gaussian-surface'
          : 'cartoon'

        for (const c of s.components) {
          await plugin.builders.structure.representation.addRepresentation(c.cell, {
            type: reprType as any,
          })
        }
      }
    } catch (err) {
      console.warn('Representation change failed:', err)
    }
  }, [])

  /** Reset camera */
  const resetCamera = useCallback(() => {
    const viewer = viewerRef.current
    if (!viewer) return
    viewer.plugin.managers.camera.reset()
  }, [])

  /** Toggle spin animation */
  const [spinning, setSpinning] = useState(false)
  const toggleSpin = useCallback(() => {
    const viewer = viewerRef.current
    if (!viewer) return
    const newVal = !spinning
    setSpinning(newVal)
    if (newVal) {
      viewer.plugin.canvas3d?.requestCameraReset({ durationMs: 0 })
      viewer.plugin.canvas3d?.setProps({ trackball: { animate: { name: 'spin', params: { speed: 1 } } } })
    } else {
      viewer.plugin.canvas3d?.setProps({ trackball: { animate: { name: 'off', params: {} } } })
    }
  }, [spinning])

  /** Toggle fullscreen */
  const toggleFullscreen = useCallback(() => {
    setIsFullscreen(prev => !prev)
  }, [])

  /** Render the 3D viewer viewport */
  const renderViewport = (ref: React.RefObject<HTMLDivElement | null>, minH?: number) => (
    <div
      ref={ref}
      className={css.viewport}
      style={{ minHeight: minH ?? height }}
    />
  )

  /* Loading state */
  if (!filePath && !data) {
    return (
      <div className={css.container} style={{ height }}>
        <div className={css.fallback}>
          <span>📦</span>
          <span>No structure file selected</span>
        </div>
      </div>
    )
  }

  /* Error state */
  if (error && !loading) {
    return (
      <div className={css.container} style={{ height }}>
        <div className={css.fallback}>
          <span>⚠️</span>
          <span>{error}</span>
        </div>
      </div>
    )
  }

  return (
    <>
      {/* Inline viewer */}
      <div className={css.container} style={{ height }}>
        {loading && (
          <div className={css.fallback}>
            <div className={css.spinner} />
            <span>Loading 3D structure…</span>
          </div>
        )}

        {renderViewport(containerRef, height)}

        {/* Toolbar */}
        {showToolbar && !loading && (
          <div className={css.toolbar}>
            {/* Representation picker */}
            <button
              className={css.toolBtn}
              onClick={() => setShowReprMenu(!showReprMenu)}
              title="Change representation"
            >
              🎨
            </button>

            {/* Spin toggle */}
            <button
              className={`${css.toolBtn} ${spinning ? css.toolBtnActive : ''}`}
              onClick={toggleSpin}
              title={spinning ? 'Stop spin' : 'Spin'}
            >
              🔄
            </button>

            {/* Reset camera */}
            <button
              className={css.toolBtn}
              onClick={resetCamera}
              title="Reset camera"
            >
              🎯
            </button>

            {/* Fullscreen toggle */}
            {allowFullscreen && (
              <button
                className={css.toolBtn}
                onClick={toggleFullscreen}
                title="Full screen"
              >
                ⛶
              </button>
            )}

            {/* Representation dropdown */}
            {showReprMenu && (
              <div className={css.reprDropdown}>
                {(['cartoon', 'ball-and-stick', 'spacefill', 'surface'] as RepresentationType[]).map(t => (
                  <button
                    key={t}
                    className={`${css.reprOption} ${repr === t ? css.reprOptionActive : ''}`}
                    onClick={() => changeRepresentation(t)}
                  >
                    {t === 'cartoon' && '🎗️ Cartoon'}
                    {t === 'ball-and-stick' && '⚛️ Ball & Stick'}
                    {t === 'spacefill' && '🔵 Spacefill'}
                    {t === 'surface' && '🫧 Surface'}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {label && <span className={css.label}>{label}</span>}
      </div>

      {/* Fullscreen overlay */}
      {isFullscreen && (
        <div className={css.fullscreenOverlay}>
          <div className={css.fullscreenHeader}>
            <span className={css.fullscreenTitle}>🧬 {label || 'Structure Viewer'}</span>
            <button className={css.toolBtn} onClick={toggleFullscreen} title="Close">✕</button>
          </div>
          <div className={css.fullscreenBody}>
            {renderViewport(fullscreenContainerRef)}
          </div>
        </div>
      )}
    </>
  )
}
