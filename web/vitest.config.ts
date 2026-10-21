import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'

const threeDmolEsm = fileURLToPath(
  new URL('./node_modules/3dmol/build/3Dmol.es6.js', import.meta.url),
)

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: [
      { find: /^3dmol$/, replacement: threeDmolEsm },
      { find: '@', replacement: fileURLToPath(new URL('./src', import.meta.url)) },
    ],
  },
  test: {
    environment: 'jsdom',
    include: ['src/**/*.spec.ts'],
  },
})
