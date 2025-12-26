import { Page } from '@playwright/test';
import { ai } from '@zerostep/playwright';
import mockData from '../mockData.json' with { type: 'json' };
import {
  fillSupplierField,
  fillEstimatedArrivalField,
  fillReferenceNumberField,
  fillNoteToSupplierField,
  fillTagsField,
} from './purchase-order-fields';

/**
 * Fills in the purchase order form with data from mockData.json
 * @param page - Playwright page object
 * @param test - Playwright test fixture from AiFixture
 * @param order - Order object from mockData to use for filling the form
 */
export async function fillPurchaseOrderForm(page: Page, test: any, order?: any): Promise<void> {
  // Use provided order or default to first order
  const orderToUse = order || mockData.orders[0];
  if (!orderToUse) {
    throw new Error('No orders found in mockData.json');
  }

  console.log(`Filling form for order: ${orderToUse.orderConfirmationNumber}`);

  // Fill Supplier field
  await fillSupplierField(page, test);

  // Fill Payment terms (optional - skip if not needed)
  // This can be left as "None" if not specified

  // Fill Estimated arrival (shipDate)
  await fillEstimatedArrivalField(page, test, orderToUse.shipDate);


  // Fill Reference number
  await fillReferenceNumberField(page, test, orderToUse.orderConfirmationNumber);

  // Fill Note to supplier (using headline or order info)
  await fillNoteToSupplierField(page, test, orderToUse.orderConfirmationNumber, orderToUse.headline);

  // Fill Tags (optional - can use brandName or orderConfirmationNumber)
  await fillTagsField(page, test, orderToUse.brandName);

  console.log('Form fields filled successfully');
}

/**
 * Selects one random product from the recommended list using AI, then closes the popup
 * @param page - Playwright page object
 * @param test - Playwright test fixture from AiFixture
 */
export async function selectProductsWithAI(page: Page, test: any): Promise<void> {
  console.log('Opening product selection modal...');

  // Click on Browse button to open the product modal
  await page.locator('button:has-text("Browse")').click();
  await page.waitForTimeout(2000);

  // Wait for the modal/dialog to be visible
  await page.waitForTimeout(1000);

  // Use AI to select one random product from the list
  console.log('Using AI to select a random product...');
  const aiArgs = { page, test };
  await ai(
    'Select one random product from the product list by checking its checkbox. Choose any available product.',
    aiArgs
  );
  await page.waitForTimeout(1000);

  // After selecting product, click Add button to close the popup
  console.log('Adding selected products and closing popup...');
  await page.locator('button.Polaris-Button--variantPrimary:has-text("Add")').click();

  await page.waitForTimeout(2000);
  console.log('Products selected successfully');
}
