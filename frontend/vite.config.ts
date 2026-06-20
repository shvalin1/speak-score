import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { fileURLToPath, URL } from 'node:url'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    // react-router-dom 等が別実体の React を取り込み「Invalid hook call (more than
    // one copy of React)」になるのを防ぐ。単一の react/react-dom に強制 dedupe する。
    dedupe: ['react', 'react-dom'],
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
  optimizeDeps: {
    // react-router v7 等の CJS 依存が react を別チャンクに二重バンドルし
    // 「Invalid hook call (more than one copy of React)」を起こすのを防ぐ。
    // react/react-dom と同一バッチで pre-bundle して単一実体に揃える。
    include: ['react', 'react-dom', 'react-dom/client', 'react/jsx-runtime', 'react-router-dom'],
  },
})
