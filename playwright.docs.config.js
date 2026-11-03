const {defineConfig} = require('@playwright/test');
const port = Number(process.env.F1_DOCS_TEST_PORT || 4174);
const docsPath = process.env.F1_DOCS_BASE_URL || '/f1_sensor/';
const buildDir = process.env.F1_DOCS_TEST_BUILD_DIR || 'build';
const baseURL = `http://127.0.0.1:${port}${docsPath}`;

module.exports = defineConfig({
  testDir: './docs-tests',
  testMatch: '**/*.spec.js',
  outputDir: 'test-results/docs',
  fullyParallel: false,
  workers: 2,
  forbidOnly: Boolean(process.env.CI),
  retries: 0,
  reporter: [['line'], ['html', {outputFolder: 'playwright-report/docs', open: 'never'}]],
  use: {
    baseURL,
    browserName: 'chromium',
    locale: 'en-GB',
    reducedMotion: 'reduce',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  webServer: {
    command: `npm run serve -- --host 127.0.0.1 --port ${port} --dir ${buildDir}`,
    url: baseURL,
    reuseExistingServer: !process.env.CI,
    timeout: 30000,
  },
});
