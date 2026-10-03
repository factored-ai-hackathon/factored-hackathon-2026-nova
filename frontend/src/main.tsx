import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.tsx'
import { initIdleSwitchFromUrl } from './config/idleTimer'

const root = document.getElementById('root')
if (!root) throw new Error('Root element not found')

initIdleSwitchFromUrl() // ?idle=off|on, read once before any routing

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
