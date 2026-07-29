import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig(({ command }) => ({
  plugins: [react()],
  // Only prefix in production builds (GitHub Pages serves this repo at
  // /migration-factory/); `vite dev` stays at the root so local dev URLs
  // don't need the extra path segment.
  base: command === 'build' ? '/migration-factory/' : '/',
  build: {
    outDir: 'dist',
  },
}))
