/* ================================================================
   GuidedTour — Spotlight tour that highlights real UI elements
   Points at each element, blurs the rest, shows a tooltip card.
   ================================================================ */

import { useState, useEffect, useCallback, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import gt from './GuidedTour.module.css'

export interface TourStep {
  /** CSS selector for the target element (e.g. '[data-tour="sidebar-nav"]') */
  target: string
  /** Emoji shown in the tooltip */
  emoji: string
  /** Bold title */
  title: string
  /** Description paragraph */
  description: string
  /** Route to navigate to before highlighting (optional) */
  route?: string
  /** Tooltip placement relative to the highlighted element */
  placement?: 'top' | 'bottom' | 'left' | 'right'
}

interface GuidedTourProps {
  steps: TourStep[]
  onComplete: () => void
}

interface Rect {
  top: number
  left: number
  width: number
  height: number
}

const PAD = 8 // spotlight padding around element

export default function GuidedTour({ steps, onComplete }: GuidedTourProps) {
  const navigate = useNavigate()
  const [step, setStep] = useState(0)
  const [rect, setRect] = useState<Rect | null>(null)
  const [tooltipStyle, setTooltipStyle] = useState<React.CSSProperties>({})
  const tooltipRef = useRef<HTMLDivElement>(null)
  const current = steps[step]
  const isLast = step === steps.length - 1

  /* ---- Measure the target element ---- */
  const measure = useCallback(() => {
    const el = document.querySelector(current.target) as HTMLElement | null
    if (!el) { setRect(null); return }
    const r = el.getBoundingClientRect()
    setRect({
      top: r.top - PAD,
      left: r.left - PAD,
      width: r.width + PAD * 2,
      height: r.height + PAD * 2,
    })
  }, [current.target])

  /* ---- Navigate to route if needed + measure ---- */
  useEffect(() => {
    if (current.route) {
      navigate(current.route)
      // Wait for next frame so the page renders the target
      const raf = requestAnimationFrame(() => {
        setTimeout(measure, 120)
      })
      return () => cancelAnimationFrame(raf)
    } else {
      measure()
    }
  }, [step, current.route, navigate, measure])

  /* ---- Re-measure on resize ---- */
  useEffect(() => {
    window.addEventListener('resize', measure)
    return () => window.removeEventListener('resize', measure)
  }, [measure])

  /* ---- Position tooltip relative to spotlight ---- */
  useEffect(() => {
    if (!rect) return
    const placement = current.placement ?? 'bottom'
    const tooltipW = 380
    const tooltipH = 220 // approximate
    const gap = 16
    let top = 0
    let left = 0

    switch (placement) {
      case 'bottom':
        top = rect.top + rect.height + gap
        left = rect.left + rect.width / 2 - tooltipW / 2
        break
      case 'top':
        top = rect.top - tooltipH - gap
        left = rect.left + rect.width / 2 - tooltipW / 2
        break
      case 'right':
        top = rect.top + rect.height / 2 - tooltipH / 2
        left = rect.left + rect.width + gap
        break
      case 'left':
        top = rect.top + rect.height / 2 - tooltipH / 2
        left = rect.left - tooltipW - gap
        break
    }

    // Clamp to viewport
    left = Math.max(12, Math.min(left, window.innerWidth - tooltipW - 12))
    top = Math.max(12, Math.min(top, window.innerHeight - tooltipH - 12))

    setTooltipStyle({ top, left, width: tooltipW })
  }, [rect, current.placement])

  /* ---- Keyboard ---- */
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onComplete()
      if (e.key === 'ArrowRight' || e.key === 'Enter') handleNext()
      if (e.key === 'ArrowLeft') handlePrev()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  })

  const handleNext = () => {
    if (isLast) onComplete()
    else setStep((s) => s + 1)
  }

  const handlePrev = () => {
    if (step > 0) setStep((s) => s - 1)
  }

  /* ---- SVG cutout mask: full-screen overlay with a rectangular hole ---- */
  const renderOverlay = () => {
    const w = window.innerWidth
    const h = window.innerHeight

    if (!rect) {
      // No target found — show full dim overlay
      return (
        <div className={gt.overlay}>
          <div className={gt.fullDim} />
        </div>
      )
    }

    // Create an SVG mask with a transparent hole where the spotlight is
    return (
      <div className={gt.overlay}>
        <svg className={gt.maskSvg} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none">
          <defs>
            <mask id="tour-mask">
              <rect x={0} y={0} width={w} height={h} fill="white" />
              <rect
                x={rect.left}
                y={rect.top}
                width={rect.width}
                height={rect.height}
                rx={12}
                fill="black"
              />
            </mask>
          </defs>
          <rect
            x={0}
            y={0}
            width={w}
            height={h}
            fill="rgba(0,0,0,0.72)"
            mask="url(#tour-mask)"
          />
        </svg>

        {/* Spotlight highlight border */}
        <div
          className={gt.spotlight}
          style={{
            top: rect.top,
            left: rect.left,
            width: rect.width,
            height: rect.height,
          }}
        />
      </div>
    )
  }

  return (
    <div className={gt.tourRoot}>
      {renderOverlay()}

      {/* Tooltip card */}
      <div ref={tooltipRef} className={gt.tooltip} style={tooltipStyle} role="dialog" aria-labelledby="tour-step-title">
        {/* Arrow nub (points towards placement) */}
        <div className={`${gt.arrow} ${gt[`arrow_${current.placement ?? 'bottom'}`]}`} />

        <div className={gt.tooltipHeader}>
          <span className={gt.tooltipEmoji}>{current.emoji}</span>
          <h3 className={gt.tooltipTitle} id="tour-step-title">{current.title}</h3>
          <button className={gt.closeBtn} onClick={onComplete} title="Close tour" aria-label="Close tour">✕</button>
        </div>

        <p className={gt.tooltipDesc}>{current.description}</p>

        <div className={gt.tooltipFooter}>
          <button className={gt.skipBtn} onClick={onComplete} aria-label="Skip tour">
            ⏩ Skip Tour
          </button>

          <div className={gt.dots}>
            {steps.map((_, i) => (
              <span
                key={i}
                className={`${gt.dot} ${i === step ? gt.dotActive : i < step ? gt.dotDone : ''}`}
              />
            ))}
          </div>

          <div className={gt.navBtns}>
            {step > 0 && (
              <button className={gt.prevBtn} onClick={handlePrev} aria-label="Previous step">←</button>
            )}
            <button className={gt.nextBtn} onClick={handleNext}>
              {isLast ? 'Finish' : 'Next'} {isLast ? '🎉' : '›'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
