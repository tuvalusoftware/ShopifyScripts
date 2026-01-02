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

interface OrderItem {
  orderItemId: number;
  productName: string;
  sku: string;
  quantity: number;
}

export async function fillPurchaseOrderForm(page: Page, test: any, order?: any): Promise<void> {
  const orderToUse = order || mockData.orders[0];
  if (!orderToUse) {
    throw new Error('No orders found in mockData.json');
  }

  console.log(`Filling form for order: ${orderToUse.orderConfirmationNumber}`);

  await fillSupplierField(page, test);
  await fillEstimatedArrivalField(page, test, orderToUse.shipDate);
  await fillReferenceNumberField(page, test, orderToUse.orderConfirmationNumber);
  await fillNoteToSupplierField(page, test, orderToUse.orderConfirmationNumber, orderToUse.headline);
  await fillTagsField(page, test, orderToUse.brandName);

  console.log('Form fields filled successfully');
}

export async function selectProductsFromOrder(page: Page, test: any, items: OrderItem[]): Promise<void> {
  if (!items || items.length === 0) {
    console.log('No items to select, skipping product selection');
    return;
  }

  console.log(`Selecting ${items.length} products from order (one by one)...`);

  const aiArgs = { page, test };

  for (let i = 0; i < items.length; i++) {
    const item = items[i];
    const searchTerm = item.sku || item.productName;
    console.log(`\n[${i + 1}/${items.length}] Processing product: ${searchTerm}`);

    await page.locator('button:has-text("Browse")').click();
    await page.waitForTimeout(i === 0 ? 3000 : 2000);

    const searchInput = page.locator('input[type="search"], input[placeholder*="Search"], input[aria-label*="Search"]').first();

    try {
      await searchInput.waitFor({ state: 'visible', timeout: 5000 });
      await searchInput.clear();
      await searchInput.fill(searchTerm);
      await page.waitForTimeout(2500);
      await page.waitForLoadState('networkidle');

      await ai(
        `Find and click the checkbox for the product that matches "${searchTerm}". If there are multiple results, select the first one that best matches. Make sure to click directly on the checkbox.`,
        aiArgs
      );
      await page.waitForTimeout(1000);

      console.log(`Selected product: ${searchTerm}`);
    } catch (error) {
      console.warn(`Could not find product: ${searchTerm}, trying with product name...`);

      if (item.sku && item.productName) {
        try {
          await searchInput.clear();
          await searchInput.fill(item.productName);
          await page.waitForTimeout(2500);
          await page.waitForLoadState('networkidle');

          await ai(
            `Find and click the checkbox for the product that matches "${item.productName}". Select the first matching result. Make sure to click directly on the checkbox.`,
            aiArgs
          );
          await page.waitForTimeout(1000);
          console.log(`Selected product by name: ${item.productName}`);
        } catch (e) {
          console.error(`Failed to find product: ${item.productName}`);
        }
      }
    }

    console.log('Adding product and closing modal...');
    const addButton = page.locator('.Polaris-InlineStack button:has-text("Add")');
    const doneButton = page.locator('.Polaris-InlineStack button:has-text("Done")');

    if (await doneButton.isVisible()) {
      await doneButton.click();
    } else {
      await addButton.click();
    }
    await page.waitForTimeout(2000);
  }

  console.log(`\nSuccessfully processed ${items.length} products`);
}

export async function selectProductsWithAI(page: Page, test: any): Promise<void> {
  console.log('Opening product selection modal...');

  await page.locator('button:has-text("Browse")').click();
  await page.waitForTimeout(2000);
  await page.waitForTimeout(1000);

  console.log('Using AI to select a random product...');
  const aiArgs = { page, test };
  await ai(
    'Select one random product from the product list by checking its checkbox. Choose any available product.',
    aiArgs
  );
  await page.waitForTimeout(1000);

  console.log('Adding selected products and closing popup...');
  await page.locator('.Polaris-InlineStack button:has-text("Add")').click();

  await page.waitForTimeout(2000);
  console.log('Products selected successfully');
}
