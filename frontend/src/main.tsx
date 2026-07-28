/* ================================================================
   main.tsx — React entry point
   ================================================================ */

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { AppProvider } from '@/context/AppContext'
import { ToastProvider } from '@/context/ToastContext'
import App from './App'
import './styles/global.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AppProvider>
      <ToastProvider>
        <App />
      </ToastProvider>
    </AppProvider>
  </StrictMode>,
)
