import { defineConfig, devices } from '@playwright/test';
import dotenv from 'dotenv';

// Load environment variables from .env file
dotenv.config();

export default defineConfig({
  testDir: './tests',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: 'html',
  timeout: 600000, // Increased timeout to 10 minutes per test
  use: {
    trace: 'on-first-retry',
    actionTimeout: 30000, // Increased action timeout to 30 seconds
    navigationTimeout: 60000, // Increased navigation timeout to 1 minute
    // Use headless: 'new' instead of classic headless mode to avoid detection
    headless: process.env.HEADLESS !== 'false' ? 'new' : false,
    ...(process.env.PROXY_SERVER && {
      proxy: {
        server: process.env.PROXY_SERVER,
        ...(process.env.PROXY_USERNAME && { username: process.env.PROXY_USERNAME }),
        ...(process.env.PROXY_PASSWORD && { password: process.env.PROXY_PASSWORD }),
      },
    }),
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
