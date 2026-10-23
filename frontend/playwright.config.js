import { defineConfig } from '@playwright/test';
const port=process.env.DUCKKING_TEST_PORT??'8875';
const baseURL=`http://127.0.0.1:${port}`;
export default defineConfig({
  workers: 1,
  testDir: './tests',
  testMatch: '**/*.spec.js',
  use: { baseURL, viewport: {width:1440,height:1050}, trace:'retain-on-failure', screenshot:'only-on-failure',
    launchOptions: {args:['--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream'],
      ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE ? {executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE}:{})} },
  webServer: { command: `uv run duckking --port ${port}`, cwd: '..', url: `${baseURL}/api/health`, reuseExistingServer: false },
  reporter: [['list'],['html',{open:'never'}]],
});
