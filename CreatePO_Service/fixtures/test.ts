import { test as base } from '@playwright/test';
import { aiFixture, type AiFixture } from '@zerostep/playwright';
import { existsSync, readFileSync } from 'fs';

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
  context: async ({ browser }, use) => {
    const storageStatePath = 'playwright/auth-state.json';
    const hasValidState = existsSync(storageStatePath) && isValidStorageState(storageStatePath);

    const context = await browser.newContext({
      // Load existing session state if available
      storageState: hasValidState ? storageStatePath : undefined,
    });

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
