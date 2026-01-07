import { Page } from '@playwright/test';
import { ai } from '@zerostep/playwright';

/**
 * Fills in the Supplier currency field
 * Defaults to Vietnamese Dong (VND) if no currency specified
 * @param page - Playwright page object
 * @param test - Playwright test fixture from AiFixture
 * @param currency - Optional currency value, defaults to VND
 */
export async function fillCurrencyField(
  page: Page,
  test: any,
  currency?: string
): Promise<void> {
  console.log('Filling Supplier currency field...');
  
  const aiArgs = { page, test };
  const currencyValue = currency || 'Vietnamese Dong (VND ₫)';
  
  await ai(
    `Set the "Supplier currency" dropdown to "${currencyValue}" or the appropriate currency option.`,
    aiArgs
  );
  await page.waitForTimeout(1000);
  
  console.log('Supplier currency field filled successfully');
}

