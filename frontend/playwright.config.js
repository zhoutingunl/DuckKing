import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './tests',
  use: { baseURL: 'http://127.0.0.1:8765', viewport: {width:1440,height:1050}, trace:'retain-on-failure', screenshot:'only-on-failure' },
  webServer: { command: 'uv run duckking', cwd: '..', url: 'http://127.0.0.1:8765/api/health', reuseExistingServer: !process.env.CI },
  reporter: [['list'],['html',{open:'never'}]],
});
