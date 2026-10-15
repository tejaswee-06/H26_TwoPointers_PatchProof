import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// The PatchProof engine (python -m patchproof.server) serves the API on 127.0.0.1:8765.
// In development, Vite proxies /api there so the browser stays same-origin.
const ENGINE = process.env.PATCHPROOF_ENGINE_URL || 'http://127.0.0.1:8765';

export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: { '/api': { target: ENGINE, changeOrigin: true } },
  },
  build: { outDir: 'dist', sourcemap: false, chunkSizeWarningLimit: 900 },
});
