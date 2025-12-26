import { test } from '../fixtures/test';
import { authenticateShopify } from '../utils/shopify-auth';
import { goToCreatePoPage } from '../utils/shopify-navigation';
import { fillPurchaseOrderForm, selectProductsWithAI } from '../utils/fill-purchase-order';
import mockData from '../mockData.json' with { type: 'json' };

test('shopify automation', async ({ page }) => {
  const aiArgs = { page, test };

  // Check if already logged in by navigating to Shopify admin
  await page.goto('https://admin.shopify.com');
  await page.waitForTimeout(7000);

  // Check if we're already logged in by looking for admin dashboard elements
  const isLoggedIn = await page
    .locator('nav, [data-testid*="navigation"], a:has-text("Products")')
    .first()
    .isVisible({ timeout: 3000 })
    .catch(() => false);

  if (!isLoggedIn) {
    // Use environment variables for username and password
    const username = process.env.USERNAME;
    const password = process.env.PASS;

    if (!username || !password) {
      throw new Error('USERNAME and PASS environment variables must be set');
    }

    // Authenticate with Shopify
    await authenticateShopify(page, username, password);
    console.log('Shopify authentication completed');
  } else {
    console.log('Already logged in, skipping authentication');
  }

  console.log('Shopify page loaded');

  // Wait for the page to fully load after login
  await page.waitForTimeout(3000);

  // Get the first 3 orders from mockData
  const firstThreeOrders = mockData.orders.slice(0, 3);

  // Run 3 cycles, each cycle processes 1 order (the first 3 orders)
  for (let cycle = 1; cycle <= 3; cycle++) {
    const order = firstThreeOrders[cycle - 1];
    console.log(`\n=== Starting Cycle ${cycle}: Processing order ${order.orderConfirmationNumber} ===`);

    // Navigate to Create Purchase Order page
    await goToCreatePoPage(page);

    // Wait for the form to load
    await page.waitForTimeout(2000);

    // Fill in the purchase order form with data from mockData.json
    await fillPurchaseOrderForm(page, test, order);

    // Select products using AI
    await selectProductsWithAI(page, test);

    // Click "Save as draft" button
    await page.locator('button[aria-label="Save as draft"]').click();
    console.log(`Purchase order ${order.orderConfirmationNumber} saved as draft`);

    // Wait for the page to fully load after saving the purchase order
    await page.waitForTimeout(5000);

    console.log(`=== Cycle ${cycle} completed ===\n`);
  }
});
