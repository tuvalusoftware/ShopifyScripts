import { test as base } from '@playwright/test';
import { aiFixture, type AiFixture } from '@zerostep/playwright';
import { existsSync, readFileSync } from 'fs';

function isValidStorageState(storageStatePath: string): boolean {
  try {
    const data = JSON.parse(readFileSync(storageStatePath, 'utf-8'));
    return Array.isArray(data.cookies);
  } catch {
    return false;
  }
}

export const test = base.extend<AiFixture>({
  ...aiFixture(base),
  context: async ({ browser }, use) => {
    const storageStatePath = 'auth-state.json';
    const hasValidState = existsSync(storageStatePath) && isValidStorageState(storageStatePath);

    const context = await browser.newContext({
      storageState: hasValidState ? storageStatePath : undefined,
    });

    try {
      await use(context);
    } finally {
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
