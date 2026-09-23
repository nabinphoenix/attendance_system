import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  timeout: 180_000,
  expect: { timeout: 10_000 },
  fullyParallel: true,
  workers: 3,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: { baseURL: 'http://127.0.0.1:3100', screenshot: 'only-on-failure', trace: 'retain-on-failure' },
  projects: [
    { name: 'desktop-chromium', use: { ...devices['Desktop Chrome'], channel: process.env.PLAYWRIGHT_CHROME_CHANNEL } },
    { name: 'android-chromium', use: { ...devices['Pixel 7'], defaultBrowserType: 'chromium', channel: process.env.PLAYWRIGHT_CHROME_CHANNEL } },
    { name: 'iphone-webkit', use: { ...devices['iPhone 13'], defaultBrowserType: 'webkit' } },
  ],
  webServer: { command: 'npm run start -- --port 3100', url: 'http://127.0.0.1:3100/login', reuseExistingServer: !process.env.CI, timeout: 120_000 },
});
