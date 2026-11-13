import { fileURLToPath, URL } from 'node:url';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { VitePWA } from 'vite-plugin-pwa';

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      strategies: 'generateSW',
      includeAssets: ['szenergy_logo.png'],
      manifest: {
        name: 'SZenergy Pro Analyser',
        short_name: 'SZenergy Pro',
        description: 'High-performance telemetry and lap analysis tool',
        theme_color: '#191B1F',
        background_color: '#191B1F',
        display: 'standalone',
        start_url: '/',
        icons: [
          {
            src: '/szenergy_logo.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'any maskable',
          },
        ],
      },
      workbox: {
        skipWaiting: true,
        clientsClaim: true,
        navigateFallback: null,
        globPatterns: ['**/*.{js,css,ico,png,svg,wasm}'],
        maximumFileSizeToCacheInBytes: 16 * 1024 * 1024,
        runtimeCaching: [
          {
            urlPattern: ({ request }) => request.mode === 'navigate',
            handler: 'NetworkFirst',
            options: {
              cacheName: 'html-navigation',
              networkTimeoutSeconds: 2,
            },
          },
        ],
      },
    }),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  worker: {
    format: 'es',
  },
  build: {
    target: 'esnext',
  },
  optimizeDeps: {
    exclude: ['telemetry-core'],
  },
});
