import { defineConfig } from 'vite';

const apiPort = Number(process.env.DUCKKING_API_PORT ?? '8765');
if (!Number.isInteger(apiPort) || apiPort < 1 || apiPort > 65535) {
  throw new Error('DUCKKING_API_PORT must be an integer between 1 and 65535');
}
const target = `http://127.0.0.1:${apiPort}`;

export default defineConfig({
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    cors: false,
    // Preserve both Host and Origin so the backend's same-origin checks also
    // protect development requests. Never rewrite an untrusted Origin.
    proxy: {
      '/api': { target, changeOrigin: false },
      '^/(ws|voice)(\\?.*)?$': {
        target, ws: true, changeOrigin: false, rewriteWsOrigin: false,
      },
    },
  },
});
