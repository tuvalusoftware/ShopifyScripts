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
  // await fillTagsField(page, test, orderToUse.brandName);

  console.log('Form fields filled successfully');
}

/**
 * Searches and selects specific products from the order items
 * Each product is processed one by one: Browse -> Search -> Select -> Add -> repeat
 * @param page - Playwright page object
 * @param test - Playwright test fixture from AiFixture
 * @param items - Array of order items to search and select
 */
export async function selectProductsFromOrder(page: Page, test: any, items: OrderItem[]): Promise<void> {
  if (!items || items.length === 0) {
    console.log('No items to select, skipping product selection');
    return;
  }

  console.log(`Selecting ${items.length} products from order (one by one)...`);

  const aiArgs = { page, test };

  // Process each item one by one
  for (let i = 0; i < items.length; i++) {
    const item = items[i];
    const searchTerm = item.sku || item.productName;
    console.log(`\n[${i + 1}/${items.length}] Processing product: ${searchTerm}`);

    // Step 1: Click Browse button to open the product modal
    await page.locator('button:has-text("Browse")').click();
    // Wait longer for first modal open (UI needs more time to initialize)
    await page.waitForTimeout(i === 0 ? 3000 : 2000);

    // Step 2: Search and select the product (existing logic)
    const searchInput = page.locator('input[type="search"], input[placeholder*="Search"], input[aria-label*="Search"]').first();
    
    try {
      await searchInput.waitFor({ state: 'visible', timeout: 5000 });
      await searchInput.clear();
      await searchInput.fill(searchTerm);
      // Wait longer for search results to fully load
      await page.waitForTimeout(2500);

      // Wait for product list to be stable before clicking
      await page.waitForLoadState('networkidle');

      // Use AI to select the matching product
      await ai(
        `Find and click the checkbox for the product that matches "${searchTerm}". If there are multiple results, select the first one that best matches. Make sure to click directly on the checkbox.`,
        aiArgs
      );
      await page.waitForTimeout(1000);

      console.log(`Selected product: ${searchTerm}`);
    } catch (error) {
      console.warn(`Could not find product: ${searchTerm}, trying with product name...`);
      
      // Fallback: try with product name if SKU search failed
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

    // Step 3: Click Add/Done button to add product and close modal
    // First time: button is "Add", subsequent times: button is "Done"
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

/**
 * Selects one random product from the recommended list using AI, then closes the popup
 * @param page - Playwright page object
 * @param test - Playwright test fixture from AiFixture
 * @deprecated Use selectProductsFromOrder instead for specific product selection
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
  await page.locator('.Polaris-InlineStack button:has-text("Add")').click();

  await page.waitForTimeout(2000);
  console.log('Products selected successfully');
}
