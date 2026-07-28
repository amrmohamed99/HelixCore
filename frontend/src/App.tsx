/* ================================================================
   App — React Router configuration
   ================================================================ */

import { useState } from 'react'
import { HashRouter, Routes, Route, Navigate } from 'react-router-dom'
import Layout from '@/components/layout/Layout'
import { OnboardingWizard } from '@/components/shared'
import Dashboard from '@/pages/Dashboard'
import PdbFetch from '@/pages/PdbFetch'
import PocketAnalysis from '@/pages/PocketAnalysis'
import BatchGenerate from '@/pages/BatchGenerate'
import Minimization from '@/pages/Minimization'
import FormatConvert from '@/pages/FormatConvert'
import AutoPipeline from '@/pages/AutoPipeline'
import Docking from '@/pages/Docking'
import Similarity from '@/pages/Similarity'
import OracleAI from '@/pages/OracleAI'
import Results from '@/pages/Results'
import About from '@/pages/About'
import CompoundFilters from '@/pages/CompoundFilters'
import ADMETProfiler from '@/pages/ADMETProfiler'
import InteractionProfiler from '@/pages/InteractionProfiler'
import ClusterAnalysis from '@/pages/ClusterAnalysis'
import AnalogGenerator from '@/pages/AnalogGenerator'
import ProjectManager from '@/pages/ProjectManager'
import PrepareReceptor from '@/pages/PrepareReceptor'
import CompareCompounds from '@/pages/CompareCompounds'
import Pharmacophore from '@/pages/Pharmacophore'
import Fragments from '@/pages/Fragments'
import ScaffoldHopping from '@/pages/ScaffoldHopping'

export default function App() {
  const [showOnboarding, setShowOnboarding] = useState(
    () => !localStorage.getItem('helix-onboarding-done'),
  )

  return (
    <>
      {showOnboarding && (
        <OnboardingWizard
          onComplete={() => {
            localStorage.setItem('helix-onboarding-done', '1')
            setShowOnboarding(false)
          }}
        />
      )}
      <HashRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/fetch" element={<PdbFetch />} />
            <Route path="/prepare" element={<PrepareReceptor />} />
            <Route path="/pocket" element={<PocketAnalysis />} />
            <Route path="/batch" element={<BatchGenerate />} />
            <Route path="/minimize" element={<Minimization />} />
            <Route path="/convert" element={<FormatConvert />} />
            <Route path="/pipeline" element={<AutoPipeline />} />
            <Route path="/docking" element={<Docking />} />
            <Route path="/similarity" element={<Similarity />} />
            <Route path="/oracle" element={<OracleAI />} />
            <Route path="/results" element={<Results />} />
            <Route path="/compare" element={<CompareCompounds />} />
            <Route path="/pharmacophore" element={<Pharmacophore />} />
            <Route path="/fragments" element={<Fragments />} />
            <Route path="/scaffold" element={<ScaffoldHopping />} />
            <Route path="/filters" element={<CompoundFilters />} />
            <Route path="/admet" element={<ADMETProfiler />} />
            <Route path="/interactions" element={<InteractionProfiler />} />
            <Route path="/cluster" element={<ClusterAnalysis />} />
            <Route path="/analogs" element={<AnalogGenerator />} />
            <Route path="/projects" element={<ProjectManager />} />
            <Route path="/about" element={<About />} />
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Route>
        </Routes>
      </HashRouter>
    </>
  )
}
