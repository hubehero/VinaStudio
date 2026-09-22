import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

const threeDmolEsm = fileURLToPath(new URL('./node_modules/3dmol/build/3Dmol.es6.js', import.meta.url))

// In development the desktop shell runs the API on a fixed port so Vite can
// proxy to it; scripts/dev.py reads the same variable.
const devApiPort = Number(process.env.VINASTUDIO_DEV_API_PORT ?? 8756)
const devApiHttp = `http://127.0.0.1:${devApiPort}`
const devApiWs = `ws://127.0.0.1:${devApiPort}`

// The bundle is served by the FastAPI process on loopback and rendered inside
// a PySide6 QWebEngineView, so relative asset paths and a fixed output
// directory (the Python package) keep the two halves in sync.
export default defineConfig({
  base: './',
  plugins: [vue()],
  resolve: {
    alias: [
      // 3Dmol publishes no "exports"/"types" field; point both the bundler and
      // TypeScript (see tsconfig paths) at the ES module build and its types.
      { find: /^3dmol$/, replacement: threeDmolEsm },
      { find: '@', replacement: fileURLToPath(new URL('./src', import.meta.url)) },
    ],
  },
  build: {
    outDir: fileURLToPath(new URL('../vinastudio/server/static', import.meta.url)),
    emptyOutDir: true,
    // 3Dmol bundles Three.js and the surface kernels, so the chem chunk is
    // legitimately large; the warning threshold reflects that.
    chunkSizeWarningLimit: 2400,
  },
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    // Development talks to the same loopback API the desktop shell runs.
    proxy: {
      '/api': { target: devApiHttp, changeOrigin: true },
      '/ws': { target: devApiWs, ws: true },
    },
  },
})
