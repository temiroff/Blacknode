import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import StandaloneSlam from './StandaloneSlam'
import './index.css'
import './standalone-slam.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <StandaloneSlam />
  </StrictMode>,
)
