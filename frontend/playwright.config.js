import { defineConfig } from '@playwright/test';
export default defineConfig({
  workers: 1,
  testDir: './tests',
  testMatch: '**/*.spec.js',
  use: { baseURL: 'http://127.0.0.1:8765', viewport: {width:1440,height:1050}, trace:'retain-on-failure', screenshot:'only-on-failure',
    launchOptions: {args:['--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream'],
      ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE ? {executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE}:{})} },
  webServer: { command: 'uv run duckking', cwd: '..', url: 'http://127.0.0.1:8765/api/health', reuseExistingServer: !process.env.CI },
  reporter: [['list'],['html',{open:'never'}]],
});
