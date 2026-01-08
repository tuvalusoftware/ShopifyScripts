import { test } from '../fixtures/test';
import { authenticateShopify } from '../utils/shopify-auth';
import { goToCreatePoPage } from '../utils/shopify-navigation';
import { fillPurchaseOrderForm, selectProductsFromOrder, selectProductsWithAI } from '../utils/fill-purchase-order';
import { readFileSync, existsSync } from 'fs';
import mockData from '../mockData.json' with { type: 'json' };

// Load order data from temp file if available, otherwise use mockData
function getOrderData() {
  const tempDataPath = process.env.ORDER_DATA_PATH;
  if (tempDataPath && existsSync(tempDataPath)) {
    try {
      const data = readFileSync(tempDataPath, 'utf-8');
      console.log('Loaded order data from temp file');
      return JSON.parse(data);
    } catch (e) {
      console.log('Failed to read temp order data, using mockData');
    }
  }
  return mockData.orders[0];
}

test('shopify automation', async ({ page, context }) => {
  const aiArgs = { page, test };

  // Check if already logged in by navigating to Shopify admin
  await page.goto('https://admin.shopify.com', { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(5000);

  // Check current URL to determine login state
  const currentUrl = page.url();
  console.log(`Current URL: ${currentUrl}`);

  // Check if we're on the admin dashboard (not login page)
  const isOnAdminPage = currentUrl.includes('admin.shopify.com/store/');

  // If redirected to login page, we need to authenticate
  const needsLogin = !isOnAdminPage && (
                     currentUrl.includes('accounts.shopify.com') || 
                     currentUrl.includes('shopify.com/login') ||
                     currentUrl.includes('/authentication'));

  if (needsLogin) {
    console.log('Not logged in, starting authentication...');
    
    // Use environment variables for username and password
    const username = process.env.SHOPIFY_USERNAME;
    const password = process.env.SHOPIFY_PASS;

    if (!username || !password) {
      throw new Error('SHOPIFY_USERNAME and SHOPIFY_PASS environment variables must be set');
    }

    // Authenticate with Shopify
    await authenticateShopify(page, username, password);
    console.log('Shopify authentication completed');
    
    // Navigate back to admin after login
    await page.goto('https://admin.shopify.com', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(5000);
    
    // Save the new session state immediately after login
    await context.storageState({ path: 'playwright/auth-state.json' });
    console.log('Session state saved after login');
  } else {
    console.log('Already logged in via cookies, skipping authentication');
  }

  console.log('Shopify page loaded');

  // Wait for the page to fully load after login
  await page.waitForTimeout(3000);

  // Get order data (from temp file or mockData)
  const order = getOrderData();
  console.log(`\n=== Processing order ${order.orderConfirmationNumber} ===`);
  console.log(`Items to process: ${order.items?.length || 0}`);

  // Navigate to Create Purchase Order page
  await goToCreatePoPage(page);

  // Wait for the form to load
  await page.waitForTimeout(2000);

  // Fill in the purchase order form
  await fillPurchaseOrderForm(page, test, order);

  // Select products - use specific items if available, otherwise random selection
  if (order.items && order.items.length > 0) {
    console.log('Selecting specific products from order...');
    await selectProductsFromOrder(page, test, order.items);
  } else {
    console.log('No specific items, selecting random product...');
    await selectProductsWithAI(page, test);
  }

  // Click "Save as draft" button
  await page.locator('button[aria-label="Save as draft"]').click();
  console.log(`Purchase order ${order.orderConfirmationNumber} saved as draft`);

  // Wait for the page to fully load after saving the purchase order
  await page.waitForTimeout(5000);

  console.log(`=== Order completed ===\n`);
});
