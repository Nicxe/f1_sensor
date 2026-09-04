const {defineConfig} = require('@playwright/test');

module.exports = defineConfig({
  testDir: './docs-tests',
  testMatch: '**/*.spec.js',
  outputDir: 'test-results/docs',
  fullyParallel: false,
  workers: 2,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: [['line'], ['html', {outputFolder: 'playwright-report/docs', open: 'never'}]],
  use: {
    baseURL: 'http://127.0.0.1:4174/f1_sensor/',
    browserName: 'chromium',
    locale: 'en-GB',
    reducedMotion: 'reduce',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  webServer: {
    command: 'npm run serve -- --host 127.0.0.1 --port 4174',
    url: 'http://127.0.0.1:4174/f1_sensor/',
    reuseExistingServer: !process.env.CI,
    timeout: 30000,
  },
});
