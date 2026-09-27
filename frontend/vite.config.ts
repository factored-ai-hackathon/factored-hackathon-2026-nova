import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // The FastAPI backend runs on :8000 (see backend/README.md).
    proxy: {
      '/v1': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
    },
  },
})
