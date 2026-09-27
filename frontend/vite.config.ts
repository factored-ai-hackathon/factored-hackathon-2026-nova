import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Proxy to backend API — configure VITE_API_URL in .env
    proxy: process.env.VITE_API_URL ? {
      '/api': {
        target: process.env.VITE_API_URL,
        changeOrigin: true,
      },
    } : undefined,
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
  },
  test: {
    environment: 'jsdom',
    globals: true,
  },
})
