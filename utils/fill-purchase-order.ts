import { Page } from '@playwright/test';
import { ai } from '@zerostep/playwright';
import mockData from '../mockData.json' with { type: 'json' };
import {
  fillSupplierField,
  fillDestinationField,
  fillCurrencyField,
  fillEstimatedArrivalField,
  fillReferenceNumberField,
  fillNoteToSupplierField,
  fillTagsField,
} from './purchase-order-fields';

/**
 * Fills in the purchase order form with data from mockData.json
 * Currently uses the first order in the list
 * @param page - Playwright page object
 * @param test - Playwright test fixture from AiFixture
 */
export async function fillPurchaseOrderForm(page: Page, test: any): Promise<void> {
  // Get the first order from mockData
  const firstOrder = mockData.orders[0];
  if (!firstOrder) {
    throw new Error('No orders found in mockData.json');
  }

  console.log(`Filling form for order: ${firstOrder.orderConfirmationNumber}`);

  // Fill Supplier field
  await fillSupplierField(page, test);

  // Fill Payment terms (optional - skip if not needed)
  // This can be left as "None" if not specified

  // Fill Estimated arrival (shipDate)
  await fillEstimatedArrivalField(page, test, firstOrder.shipDate);

//   wait for 2 seconds
await page.waitForTimeout(5000);


  // Fill Reference number
  await fillReferenceNumberField(page, test, firstOrder.orderConfirmationNumber);

  // Fill Note to supplier (using headline or order info)
  await fillNoteToSupplierField(page, test, firstOrder.orderConfirmationNumber, firstOrder.headline);

  // Fill Tags (optional - can use brandName or orderConfirmationNumber)
  await fillTagsField(page, test, firstOrder.brandName);

  console.log('Form fields filled successfully');
}

/**
 * Uses AI to intelligently search and select products from the product list
 * Based on the items in the first order
 * @param page - Playwright page object
 * @param test - Playwright test fixture from AiFixture
 */
export async function selectProductsWithAI(page: Page, test: any): Promise<void> {
  const firstOrder = mockData.orders[0];
  if (!firstOrder || !firstOrder.items || firstOrder.items.length === 0) {
    console.log('No items found in the first order, skipping product selection');
    return;
  }

  const aiArgs = { page, test };

  console.log('Opening product selection modal...');

  // Click on Browse button or search field to open the product modal
  await ai(`Click on the "Browse" button or the "Search products" field to open the product selection modal.`, aiArgs);
  await page.waitForTimeout(2000);

  // For each item in the order, search and select the matching product
  for (const item of firstOrder.items) {
    console.log(`Selecting product: ${item.productName} (SKU: ${item.sku})`);

    // Build search query from product name, SKU, color, and size
    const searchTerms = [item.productName, item.sku, item.color, item.size].filter(Boolean).join(' ');

    // Use AI to search and select the product
    await ai(
      `In the "Add products" modal, search for a product matching: "${searchTerms}". 
      The product should match the name "${item.productName}", SKU "${item.sku}", color "${item.color}", and size "${item.size}".
      Select the checkbox for the matching product variant. If multiple variants are shown, select the one that best matches the color and size.
      If the exact product is not found, select the closest matching product variant.`,
      aiArgs
    );

    await page.waitForTimeout(1500);
  }

  // After selecting all products, click Add button
  console.log('Adding selected products...');
  await ai(`Click the "Add" button in the "Add products" modal to confirm the product selection and close the modal.`, aiArgs);

  await page.waitForTimeout(2000);
  console.log('Products selected successfully');
}
