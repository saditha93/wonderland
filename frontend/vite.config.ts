import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
const targets = {
  attractions: process.env.API_ATTRACTIONS_TARGET ?? 'http://127.0.0.1:8001',
  booking: process.env.API_BOOKING_TARGET ?? 'http://127.0.0.1:8002',
  gate: process.env.API_GATE_TARGET ?? 'http://127.0.0.1:8003',
  analytics: process.env.API_ANALYTICS_TARGET ?? 'http://127.0.0.1:8004',
};
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { proxy: Object.fromEntries(Object.entries(targets).map(([key, target]) =>
    [`/api/${key}`, { target, rewrite: (path: string) => path.replace(`/api/${key}`, '') }])) },
});
