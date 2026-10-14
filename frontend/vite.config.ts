import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { fileURLToPath, URL } from 'node:url';
const targets = {
  attractions: process.env.API_ATTRACTIONS_TARGET ?? 'http://127.0.0.1:8001',
  booking: process.env.API_BOOKING_TARGET ?? 'http://127.0.0.1:8002',
  gate: process.env.API_GATE_TARGET ?? 'http://127.0.0.1:8003',
  analytics: process.env.API_ANALYTICS_TARGET ?? 'http://127.0.0.1:8004',
};
export default defineConfig(({ mode }) => ({
  root: mode === 'admin' ? fileURLToPath(new URL('./admin', import.meta.url)) : undefined,
  envDir: fileURLToPath(new URL('.', import.meta.url)),
  resolve: { alias: { '/@wonderland': fileURLToPath(new URL('./src', import.meta.url)) } },
  build: { outDir: mode === 'admin' ? '../dist-admin' : 'dist', emptyOutDir: true },
  plugins: [react(), tailwindcss()],
  server: { host: '127.0.0.1', port: mode === 'admin' ? 5174 : 5173, strictPort: true,
    fs: { allow: [fileURLToPath(new URL('.', import.meta.url))] },
    proxy: Object.fromEntries(Object.entries(targets).map(([key, target]) =>
    [`/api/${key}`, { target, rewrite: (path: string) => path.replace(`/api/${key}`, '') }])) },
}));
