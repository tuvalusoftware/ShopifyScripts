import { Page } from '@playwright/test';
import { ai } from '@zerostep/playwright';

/**
 * Fills in the Destination field using shopDomain or customerName
 * @param page - Playwright page object
 * @param test - Playwright test fixture from AiFixture
 * @param destination - The destination value (shopDomain or customerName)
 */
export async function fillDestinationField(
  page: Page,
  test: any,
  destination: string | undefined
): Promise<void> {
  if (!destination) {
    console.log('No destination value provided, skipping Destination field');
    return;
  }

  console.log(`Filling Destination field with: ${destination}`);
  
  const aiArgs = { page, test };
  await ai(
    `Fill in the "Destination" dropdown field with the value "${destination}". If the exact value is not available, select the closest matching option.`,
    aiArgs
  );
  await page.waitForTimeout(1000);
  
  console.log('Destination field filled successfully');
}

