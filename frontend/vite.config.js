import { defineConfig } from 'vite';
import { fileURLToPath } from 'node:url';

const apiPort = Number(process.env.DUCKKING_API_PORT ?? '8765');
if (!Number.isInteger(apiPort) || apiPort < 1 || apiPort > 65535) {
  throw new Error('DUCKKING_API_PORT must be an integer between 1 and 65535');
}
const target = `http://127.0.0.1:${apiPort}`;

export default defineConfig({
  base: './',
  plugins: [{
    name: 'secure-public-entry',
    configureServer(server) {
      server.middlewares.use((req,res,next)=>{
        const url=new URL(req.url,'http://localhost');
        if(url.pathname!=='/')return next();
        url.searchParams.set('sort','top');
        res.writeHead(307,{Location:'/features.html?'+url.searchParams});res.end();
      });
    },
    // Runs before application modules, in both development HTML and every built page.
    transformIndexHtml() {
      return [{tag:'script',attrs:{src:'./secure-entry.js'},injectTo:'head-prepend'}];
    },
  }],
  build: {
    rolldownOptions: {
      // Keep the graphics dependency cache stable when voice/UI code changes.
      output: {codeSplitting: {groups: [{name: 'three', test: /node_modules[\/]three/}]}},
      input: {
        main: fileURLToPath(new URL('./index.html', import.meta.url)),
        features: fileURLToPath(new URL('./features.html', import.meta.url)),
        experience: fileURLToPath(new URL('./experience.html', import.meta.url)),
        statistics: fileURLToPath(new URL('./statistics.html', import.meta.url)),
        studio: fileURLToPath(new URL('./studio.html', import.meta.url)),
        demos: fileURLToPath(new URL('./demos.html', import.meta.url)),
        scenarios: fileURLToPath(new URL('./scenarios.html', import.meta.url)),
        seesaw: fileURLToPath(new URL('./seesaw.html', import.meta.url)),
        training: fileURLToPath(new URL('./training.html', import.meta.url)),
        balance: fileURLToPath(new URL('./balance.html', import.meta.url)),
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
