import { Page } from '@playwright/test';
import { ai } from '@zerostep/playwright';

/**
 * Fills in the Tags field
 * @param page - Playwright page object
 * @param test - Playwright test fixture from AiFixture
 * @param tagValue - The tag value (typically brandName or orderConfirmationNumber)
 */
export async function fillTagsField(
  page: Page,
  test: any,
  tagValue: string | undefined
): Promise<void> {
  if (!tagValue) {
    console.log('No tag value provided, skipping Tags field');
    return;
  }

  console.log(`Filling Tags field with: ${tagValue}`);
  
  const aiArgs = { page, test };
  await ai(
    `Fill in the "Tags" field with the value "${tagValue}".`,
    aiArgs
  );
  await page.waitForTimeout(1000);
  
  console.log('Tags field filled successfully');
}

