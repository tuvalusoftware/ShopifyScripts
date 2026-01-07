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
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
