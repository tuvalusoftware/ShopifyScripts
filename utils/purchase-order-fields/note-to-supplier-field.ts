import { Page } from '@playwright/test';
import { ai } from '@zerostep/playwright';

/**
 * Fills in the Note to supplier text area
 * @param page - Playwright page object
 * @param test - Playwright test fixture from AiFixture
 * @param orderConfirmationNumber - The order confirmation number
 * @param headline - Optional headline/note content
 */
export async function fillNoteToSupplierField(
  page: Page,
  test: any,
  orderConfirmationNumber: string | undefined,
  headline?: string
): Promise<void> {
  if (!orderConfirmationNumber) {
    console.log('No order confirmation number provided, skipping Note to supplier field');
    return;
  }

  const noteToSupplier = headline
    ? `Order: ${orderConfirmationNumber}\n${headline}`
    : `Order: ${orderConfirmationNumber}`;

  console.log(`Filling Note to supplier field with order: ${orderConfirmationNumber}`);
  
  const aiArgs = { page, test };
  await ai(
    `Fill in the "Note to supplier" text area with the following text: "${noteToSupplier}". Make sure to stay within the character limit.`,
    aiArgs
  );
  await page.waitForTimeout(1000);
  
  console.log('Note to supplier field filled successfully');
}

