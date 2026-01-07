import { test as base } from '@playwright/test';
import { aiFixture, type AiFixture } from '@zerostep/playwright';
import { existsSync } from 'fs';

// Create a persistent browser context
export const test = base.extend<AiFixture>({
  ...aiFixture(base),
  context: async ({ browser }, use) => {
    const storageStatePath = 'auth-state.json';
    const hasExistingState = existsSync(storageStatePath);

    const context = await browser.newContext({
      // Load existing session state if available
      storageState: hasExistingState ? storageStatePath : undefined,
    });

    try {
      await use(context);
    } finally {
      // Save session state after tests (even if test fails)
      try {
        await context.storageState({ path: storageStatePath });
      } catch (error) {
        console.warn('Failed to save storage state:', error);
      }
      await context.close();
    }
  },
});
