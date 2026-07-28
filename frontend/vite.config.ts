import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import electron from 'vite-plugin-electron'
import renderer from 'vite-plugin-electron-renderer'
import path from 'path'
import fs from 'fs'

/* Copy static Electron assets (splash.html) to dist-electron */
function copyElectronAssets() {
  return {
    name: 'copy-electron-assets',
    closeBundle() {
      const src = path.resolve(__dirname, 'electron', 'splash.html')
      const destDir = path.resolve(__dirname, 'dist-electron')
      const dest = path.join(destDir, 'splash.html')
      if (fs.existsSync(src)) {
        fs.mkdirSync(destDir, { recursive: true })
        fs.copyFileSync(src, dest)
      }
    },
  }
}

export default defineConfig({
  plugins: [
    react(),
    electron([
      {
        entry: 'electron/main.ts',
        onstart(args) {
          args.startup()
        },
        vite: {
          build: {
            outDir: 'dist-electron',
            rollupOptions: {
              external: ['electron'],
            },
          },
        },
      },
      {
        entry: 'electron/preload.ts',
        onstart(args) {
          args.reload()
        },
        vite: {
          build: {
            outDir: 'dist-electron',
            rollupOptions: {
              external: ['electron'],
            },
          },
        },
      },
    ]),
    renderer(),
    copyElectronAssets(),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
})
