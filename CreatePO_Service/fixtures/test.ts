import { test as base } from '@playwright/test';
import { chromium } from 'playwright-extra';
import StealthPlugin from 'puppeteer-extra-plugin-stealth';
import { aiFixture, type AiFixture } from '@zerostep/playwright';
import { existsSync, readFileSync } from 'fs';
import dotenv from 'dotenv';

// Load environment variables from .env file
dotenv.config();

// Use stealth plugin to avoid detection
chromium.use(StealthPlugin());

// Check if storage state file is valid JSON
function isValidStorageState(storageStatePath: string): boolean {
  try {
    const data = JSON.parse(readFileSync(storageStatePath, 'utf-8'));
    // Just check if it has cookies array - let Playwright handle the rest
    return Array.isArray(data.cookies);
  } catch {
    return false;
  }
}

// Create a persistent browser context
export const test = base.extend<AiFixture>({
  ...aiFixture(base),
  browser: async ({}, use) => {
    // Override browser to use playwright-extra chromium with stealth plugin
    const launchOptions = {
      // Note: playwright-extra doesn't support 'new' headless mode
      // Use true for headless or false for headed mode
      headless: process.env.HEADLESS !== 'false',
      ...(process.env.PROXY_SERVER && {
        proxy: {
          server: process.env.PROXY_SERVER,
          ...(process.env.PROXY_USERNAME && { username: process.env.PROXY_USERNAME }),
          ...(process.env.PROXY_PASSWORD && { password: process.env.PROXY_PASSWORD }),
        },
      }),
    };

    const browser = await chromium.launch(launchOptions);
    await use(browser as any);
    await browser.close();
  },
  context: async ({ browser }, use) => {
    const storageStatePath = 'playwright/auth-state.json';
    const hasValidState = existsSync(storageStatePath) && isValidStorageState(storageStatePath);

    const contextOptions: Parameters<typeof browser.newContext>[0] = {
      // Load existing session state if available
      storageState: hasValidState ? storageStatePath : undefined,
      // Proxy configuration for Cloudflare bypass
      ...(process.env.PROXY_SERVER && {
        proxy: {
          server: process.env.PROXY_SERVER,
          ...(process.env.PROXY_USERNAME && { username: process.env.PROXY_USERNAME }),
          ...(process.env.PROXY_PASSWORD && { password: process.env.PROXY_PASSWORD }),
        },
      }),
    };

    const context = await browser.newContext(contextOptions);

    try {
      await use(context);
    } finally {
      // Save session state after tests (even if test fails)
      try {
        await context.storageState({ path: storageStatePath });
        console.log('Session state saved successfully');
      } catch (error) {
        console.warn('Failed to save storage state:', error);
      }
      await context.close();
    }
  },
});
