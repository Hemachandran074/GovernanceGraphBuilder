import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  build: {
    // The graph library (Cytoscape) is code-split via React.lazy in App.tsx,
    // so the initial app chunk stays small.
    chunkSizeWarningLimit: 900,
  },
})
