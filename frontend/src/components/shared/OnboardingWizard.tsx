/* ================================================================
   OnboardingWizard — First-run setup guide
   ================================================================ */

import { useState } from 'react'
import ob from './OnboardingWizard.module.css'

interface OnboardingWizardProps {
  onComplete: () => void
}

const steps = [
  {
    emoji: '🧬',
    title: 'Welcome to Helix Core',
    description:
      'Helix Core is a full-featured drug discovery suite that guides you from protein retrieval all the way through docking and AI-powered rescoring.',
  },
  {
    emoji: '📥',
    title: 'Step 1 — Fetch Protein',
    description:
      'Start by entering a PDB ID (e.g. 1HSG) on the Fetch page. Helix Core pulls the unmodified structure from RCSB; use Prepare Receptor next to create a docking-ready PDBQT.',
  },
  {
    emoji: '🔬',
    title: 'Step 2 — Analyze & Generate',
    description:
      'Use Pocket Analysis to identify binding sites, then Batch Generate ligands from a SMILES list. Minimize and convert them to PDBQT format.',
  },
  {
    emoji: '🧲',
    title: 'Step 3 — Dock & Score',
    description:
      'Run AutoDock Vina docking, then use Oracle AI for ML-based rescoring. Browse top-ranked candidates in the Results Explorer.',
  },
  {
    emoji: '📋',
    title: 'Step 4 — Export & Share',
    description:
      'Export top candidates and generate CSV reports with ADMET properties. Use the Pipeline view on the Dashboard to track your progress.',
  },
]

export default function OnboardingWizard({ onComplete }: OnboardingWizardProps) {
  const [step, setStep] = useState(0)

  const isLast = step === steps.length - 1
  const current = steps[step]

  const handleNext = () => {
    if (isLast) {
      onComplete()
    } else {
      setStep((s) => s + 1)
    }
  }

  return (
    <div className={ob.overlay}>
      <div className={ob.dialog} role="dialog" aria-labelledby="wizard-title" aria-modal="true">
        <div className={ob.progress} role="group" aria-label={`Step ${step + 1} of ${steps.length}`}>
          {steps.map((_, i) => (
            <div
              key={i}
              className={`${ob.dot} ${i === step ? ob.dotActive : i < step ? ob.dotDone : ''}`}
            />
          ))}
        </div>

        <div className={ob.emoji}>{current.emoji}</div>
        <h2 id="wizard-title" className={ob.title}>{current.title}</h2>
        <p className={ob.description}>{current.description}</p>

        <div className={ob.actions}>
          {step > 0 && (
            <button className={ob.btnSecondary} onClick={() => setStep((s) => s - 1)}>
              ← Back
            </button>
          )}
          <button className={ob.btnPrimary} onClick={handleNext}>
            {isLast ? 'Get Started 🚀' : 'Next →'}
          </button>
        </div>

        <button className={ob.skip} onClick={onComplete}>
          Skip intro
        </button>
      </div>
    </div>
  )
}
