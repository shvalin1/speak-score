import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { fileURLToPath, URL } from 'node:url'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      // shared/mock_data などモノレポ共有資産を @shared で参照
      '@shared': fileURLToPath(new URL('../shared', import.meta.url)),
      // shadcn/ui のコンポーネントが想定する @ エイリアス（src 直下）
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    // モノレポ外（../shared）のJSONを読むため許可
    fs: { allow: ['..'] },
    // docker-composeを使わずVite単体で開発する場合のフォールバック:
    // /api をローカルbackendへproxy（本番はNginxが担う）
    proxy: {
      '/api': {
        target: process.env.VITE_PROXY_TARGET ?? 'http://localhost:8080',
        changeOrigin: true,
      },
    },
  },
})
