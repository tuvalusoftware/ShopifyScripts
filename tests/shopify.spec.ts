import { test } from '../fixtures/test';
import { authenticateShopify } from '../utils/shopify-auth';
import { goToCreatePoPage } from '../utils/shopify-navigation';
import { fillPurchaseOrderForm, selectProductsWithAI } from '../utils/fill-purchase-order';

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

  // Navigate to Create Purchase Order page
  await goToCreatePoPage(page);

  // Wait for the form to load
  await page.waitForTimeout(2000);

  // Fill in the purchase order form with data from mockData.json
  await fillPurchaseOrderForm(page, test);

  // Select products using AI
  await selectProductsWithAI(page, test);
});
