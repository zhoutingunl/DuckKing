import { defineConfig } from 'vite';
import { fileURLToPath } from 'node:url';

const apiPort = Number(process.env.DUCKKING_API_PORT ?? '8765');
if (!Number.isInteger(apiPort) || apiPort < 1 || apiPort > 65535) {
  throw new Error('DUCKKING_API_PORT must be an integer between 1 and 65535');
}
const target = `http://127.0.0.1:${apiPort}`;

export default defineConfig({
  base: './',
  build: {
    rolldownOptions: {
      input: {
        main: fileURLToPath(new URL('./index.html', import.meta.url)),
        statistics: fileURLToPath(new URL('./statistics.html', import.meta.url)),
        studio: fileURLToPath(new URL('./studio.html', import.meta.url)),
        demos: fileURLToPath(new URL('./demos.html', import.meta.url)),
        scenarios: fileURLToPath(new URL('./scenarios.html', import.meta.url)),
        deploys: fileURLToPath(new URL('./deploys.html', import.meta.url)),
      },
    },
  },
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    cors: false,
    // Preserve both Host and Origin so the backend's same-origin checks also
    // protect development requests. Never rewrite an untrusted Origin.
    proxy: {
      '/api': { target, changeOrigin: false },
      '^/(ws|voice|scene-ws|scene-voice)(\\?.*)?$': {
        target, ws: true, changeOrigin: false, rewriteWsOrigin: false,
      },
    },
  },
});
