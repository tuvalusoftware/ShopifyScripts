import { test } from '../fixtures/test';
import { authenticateShopify } from '../utils/shopify-auth';
import { goToCreatePoPage } from '../utils/shopify-navigation';
import { fillPurchaseOrderForm, selectProductsFromOrder, selectProductsWithAI } from '../utils/fill-purchase-order';
import { readFileSync, existsSync } from 'fs';
import mockData from '../mockData.json' with { type: 'json' };

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

  await page.goto('https://admin.shopify.com', { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(5000);

  const currentUrl = page.url();
  console.log(`Current URL: ${currentUrl}`);

  const isOnAdminPage = currentUrl.includes('admin.shopify.com/store/');
  const needsLogin = !isOnAdminPage && (
    currentUrl.includes('accounts.shopify.com') ||
    currentUrl.includes('shopify.com/login') ||
    currentUrl.includes('/authentication')
  );

  if (needsLogin) {
    console.log('Not logged in, starting authentication...');

    const username = process.env.SHOPIFY_USERNAME;
    const password = process.env.SHOPIFY_PASS;

    if (!username || !password) {
      throw new Error('SHOPIFY_USERNAME and SHOPIFY_PASS environment variables must be set');
    }

    await authenticateShopify(page, username, password);
    console.log('Shopify authentication completed');

    await page.goto('https://admin.shopify.com', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(5000);

    await context.storageState({ path: 'auth-state.json' });
    console.log('Session state saved after login');
  } else {
    console.log('Already logged in via cookies, skipping authentication');
  }

  console.log('Shopify page loaded');
  await page.waitForTimeout(3000);

  const order = getOrderData();
  console.log(`\n=== Processing order ${order.orderConfirmationNumber} ===`);
  console.log(`Items to process: ${order.items?.length || 0}`);

  await goToCreatePoPage(page);
  await page.waitForTimeout(2000);

  await fillPurchaseOrderForm(page, test, order);

  if (order.items && order.items.length > 0) {
    console.log('Selecting specific products from order...');
    await selectProductsFromOrder(page, test, order.items);
  } else {
    console.log('No specific items, selecting random product...');
    await selectProductsWithAI(page, test);
  }

  await page.locator('button[aria-label="Save as draft"]').click();
  console.log(`Purchase order ${order.orderConfirmationNumber} saved as draft`);

  await page.waitForTimeout(5000);
  console.log(`=== Order completed ===\n`);
});
