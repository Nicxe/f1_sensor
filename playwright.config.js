const { defineConfig } = require('@playwright/test');

module.exports = defineConfig({
  testDir: './frontend-tests',
  testMatch: '**/*.spec.js',
  grepInvert: process.env.F1_MAINTENANCE ? undefined : /@performance/,
  outputDir: 'test-results/playwright',
  snapshotPathTemplate: '{testDir}/{testFilePath}-snapshots/{arg}{ext}',
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['line'], ['html', { outputFolder: 'playwright-report', open: 'never' }]] : 'line',
  expect: {
    timeout: 5000,
    toHaveScreenshot: {
      animations: 'disabled',
      maxDiffPixelRatio: 0.01,
    },
  },
  use: {
    baseURL: 'http://127.0.0.1:4173',
    browserName: process.env.F1_BROWSER || 'chromium',
    locale: 'en-GB',
    timezoneId: 'America/Los_Angeles',
    colorScheme: 'dark',
    hasTouch: true,
    reducedMotion: 'reduce',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  webServer: {
    command: 'node frontend-tests/server.cjs',
    url: 'http://127.0.0.1:4173/frontend-tests/fixture.html',
    reuseExistingServer: !process.env.CI,
    timeout: 30000,
  },
});
