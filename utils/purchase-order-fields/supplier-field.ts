import { Page } from '@playwright/test';
import { ai } from '@zerostep/playwright';

/**
 * Fills in the Supplier field by selecting the first available option
 * @param page - Playwright page object
 * @param test - Playwright test fixture from AiFixture
 */
export async function fillSupplierField(page: Page, test: any): Promise<void> {
  console.log('Filling Supplier field...');

  // Click the supplier dropdown button
  await page.getByRole('button', { name: 'Select supplier' }).click();
  await page.waitForTimeout(1000);

  // Fill Supplier field by manually clicking the first option in the supplier dropdown
  const firstSupplierOption = page.locator('li[role="option"] >> nth=0');
  await firstSupplierOption.waitFor({ state: 'visible', timeout: 5000 });
  await firstSupplierOption.click();
  await page.waitForTimeout(1000);

  console.log('Supplier field filled successfully');
}
