import { Page } from '@playwright/test';
import { ai } from '@zerostep/playwright';

/**
 * Fills in the Tags field
 * @param page - Playwright page object
 * @param test - Playwright test fixture (kept for compatibility, not used)
 * @param tagValue - The tag value (typically brandName or orderConfirmationNumber)
 */
export async function fillTagsField(page: Page, test: any, tagValue: string | undefined): Promise<void> {
  if (!tagValue) {
    console.log('No tag value provided, skipping Tags field');
    return;
  }

  console.log(`Filling Tags field with: ${tagValue}`);

  try {
    // Find and click the Tags input field
    const tagsInput = page.locator('input[name="tags"]');
    await tagsInput.waitFor({ state: 'visible', timeout: 5000 });
    await tagsInput.click();
    await tagsInput.fill(tagValue);
    await page.waitForTimeout(500);

    // Use AI to either click "Add" button if tag doesn't exist, or select existing tag
    await ai(
      `In the tags dropdown, if there is an "Add" button for "${tagValue}", click it. If "${tagValue}" already exists as a tag option, select it instead.`,
      { page, test }
    );
    await page.waitForTimeout(1000);

    console.log('Tags field filled successfully');
  } catch (error) {
    console.error(`Error filling Tags field: ${error}`);
    throw error;
  }
}
