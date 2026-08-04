import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { copyFileSync } from 'node:fs'
import { resolve } from 'node:path'

const outputDirectory = resolve(__dirname, '../packages/blacknode-cuda/viewer')

export default defineConfig({
  root: resolve(__dirname, 'standalone-slam'),
  publicDir: false,
  plugins: [
    react(),
    {
      name: 'blacknode-slam-viewer-logo',
      writeBundle() {
        copyFileSync(
          resolve(__dirname, 'public/blacknode-logo-dark.png'),
          resolve(outputDirectory, 'blacknode-logo-dark.png'),
        )
      },
    },
  ],
  build: {
    outDir: outputDirectory,
    emptyOutDir: true,
    sourcemap: false,
  },
})
