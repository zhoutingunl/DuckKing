import { defineConfig } from '@playwright/test';
const port=process.env.DUCKKING_TEST_PORT??'8875';
const dev=process.env.DUCKKING_TEST_DEV==='1';
const devPort=process.env.DUCKKING_TEST_DEV_PORT??'8876';
for (const value of [port,devPort]) {
  if (!/^\d+$/.test(value)||Number(value)<1||Number(value)>65535) throw new Error('Invalid test port');
}
if(dev&&Number(port)===Number(devPort))throw new Error('Development and backend test ports must differ');
const apiURL=`http://127.0.0.1:${port}`;
const baseURL=dev?`http://127.0.0.1:${devPort}`:apiURL;
export default defineConfig({
  workers: 1,
  fullyParallel: true,
  testDir: './tests',
  outputDir: `test-results/${dev?'development':'production'}`,
  testMatch: '**/*.spec.js',
  testIgnore: dev?[]:['**/dev-proxy.spec.js'],
  use: { baseURL, viewport: {width:1440,height:1050}, trace:{mode:'retain-on-failure',screenshots:false}, screenshot:'only-on-failure',
    launchOptions: {args:['--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream'],
      ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE ? {executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE}:{})} },
  webServer: [
    { command: `uv run --frozen duckking --port ${port}`, cwd: '..', url: `${apiURL}/api/health`, reuseExistingServer: false,
      env:{DUCKKING_DATA_DIR:`.duckking/browser-tests/${port}`,DUCKKING_SECRETS_FILE:'.duckking/browser-tests/no-secrets.env',LINX_OTA_URL:'http://127.0.0.1:1/ota/',LINX_WS_URL:'',LINX_WS_TOKEN:'',LINX_DEVICE_ID:'',LINX_CLIENT_ID:''} },
    ...(dev?[{command:`npm run dev -- --port ${devPort}`,env:{DUCKKING_API_PORT:port},url:baseURL,reuseExistingServer:false}]:[]),
  ],
  reporter: [['list'],['html',{open:'never',outputFolder:`playwright-report/${dev?'development':'production'}`}]],
});
