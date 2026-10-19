/// <reference types="vitest/config" />
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { VitePWA } from 'vite-plugin-pwa'

const tileCache = (name: string, urlPattern: RegExp) => ({
  urlPattern,
  handler: 'CacheFirst' as const,
  options: {
    cacheName: name,
    // Solo le tessere già viste: niente scaricamenti massivi (policy OSM/OpenTopoMap).
    expiration: { maxEntries: 3000, maxAgeSeconds: 60 * 60 * 24 * 30 },
    cacheableResponse: { statuses: [0, 200] },
  },
})

export default defineConfig({
  plugins: [
    vue(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['icon.svg', 'icon-192.png', 'icon-512.png'],
      manifest: {
        name: 'fiuto',
        short_name: 'fiuto',
        description: "Dove ha senso cercare tartufo nero nell'Appennino parmense",
        lang: 'it',
        theme_color: '#3b2f2a',
        background_color: '#f6f1e7',
        display: 'standalone',
        orientation: 'portrait',
        start_url: '/',
        icons: [
          { src: 'icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: 'icon-512.png', sizes: '512x512', type: 'image/png' },
          { src: 'icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
          { src: 'icon.svg', sizes: 'any', type: 'image/svg+xml' },
        ],
      },
      workbox: {
        globPatterns: ['**/*.{js,mjs,css,html,svg,png,pbf,json,txt}'],
        maximumFileSizeToCacheInBytes: 4 * 1024 * 1024,
        navigateFallback: '/index.html',
        runtimeCaching: [
          tileCache('tiles-opentopomap', /^https:\/\/[abc]\.tile\.opentopomap\.org\//),
          tileCache('tiles-osm', /^https:\/\/tile\.openstreetmap\.org\//),
        ],
      },
    }),
  ],
  resolve: {
    alias: {
      '@model': fileURLToPath(new URL('../model', import.meta.url)),
    },
  },
  build: {
    // MapLibre da solo pesa circa 1 MB: è atteso.
    chunkSizeWarningLimit: 1200,
  },
  server: {
    fs: { allow: ['..'] },
  },
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
  },
})
