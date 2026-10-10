/* global process */
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  return {
    plugins: [react()],
    server: {
      proxy: {
        '/api': {
          target: env.VITE_API_URL || 'http://localhost:8085',
          changeOrigin: true,
        },
        '/vis': {
          target: env.VITE_VISDOM_URL || 'http://localhost:8097',
          changeOrigin: true,
          ws: true,
        }
      }
    }
  }
})

