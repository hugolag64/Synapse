import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  base: '/qcm-app/',
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8082',
    },
  },
  test: {
    environment: 'jsdom',
  },
})
