import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ command, mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  // A production build must know where the API lives: either an absolute VITE_API_BASE_URL
  // (e.g. Vercel -> Render) or VITE_API_SAME_ORIGIN=true behind a reverse proxy (docker/nginx).
  if (command === 'build' && mode === 'production') {
    const base = env.VITE_API_BASE_URL || '';
    if (!base && env.VITE_API_SAME_ORIGIN !== 'true') {
      throw new Error('Set VITE_API_BASE_URL (https://your-api.example) or VITE_API_SAME_ORIGIN=true for a production build.');
    }
    if (base && !/^https:\/\//.test(base) && !/^http:\/\/(localhost|127\.0\.0\.1)/.test(base)) {
      throw new Error(`VITE_API_BASE_URL must use https:// in production (got ${base}).`);
    }
  }
  // In development the UI talks to the API through this proxy, so no API origin (and no
  // secret of any kind) is baked into the browser bundle.
  const apiTarget = env.VITE_DEV_API_PROXY || 'http://127.0.0.1:8000';
  const proxy = {
    '/api': { target: apiTarget, changeOrigin: true },
    '/ws': { target: apiTarget.replace(/^http/, 'ws'), ws: true, changeOrigin: true },
  };

  return {
    plugins: [react()],
    server: { port: 5173, strictPort: true, proxy },
    preview: { port: 4173, proxy },
    // MapLibre 6 ships ESM + a separate module worker; keep it out of dep pre-bundling.
    optimizeDeps: { exclude: ['maplibre-gl'] },
    worker: { format: 'es' },
    build: { chunkSizeWarningLimit: 1600, sourcemap: false },
  };
});
