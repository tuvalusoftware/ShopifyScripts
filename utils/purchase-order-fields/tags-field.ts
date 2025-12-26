import { Page } from '@playwright/test';

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

    // Wait for the dropdown to appear and find the "Add" option with the tag value
    const addOption = page.locator(`li[data-listbox-option-value="___ADD__ACTION__"]:has-text("Add"):has-text("${tagValue}")`);
    await addOption.waitFor({ state: 'visible', timeout: 5000 });
    await addOption.click();
    await page.waitForTimeout(1000);

    console.log('Tags field filled successfully');
  } catch (error) {
    console.error(`Error filling Tags field: ${error}`);
    throw error;
  }
}
