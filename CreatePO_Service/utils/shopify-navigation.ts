import { Page } from '@playwright/test';

/**
 * Navigates to the Create Purchase Order page in Shopify admin
 * @param page - Playwright page object
 */
export async function goToCreatePoPage(page: Page): Promise<void> {
  // On the sidebar, click on "Products"
  const productsLink = page.locator('a:has-text("Products"), [data-testid*="products"], nav a:has-text("Products")');
  await productsLink.waitFor({ state: 'visible', timeout: 10000 });
  await productsLink.click();
  console.log('Clicked on Products');

  // Wait for navigation
  await page.waitForTimeout(2000);

  // Click on "Purchase orders"
  const purchaseOrdersLink = page.locator('a:has-text("Purchase orders"), button:has-text("Purchase orders"), [data-testid*="purchase-orders"]');
  await purchaseOrdersLink.waitFor({ state: 'visible', timeout: 10000 });
  await purchaseOrdersLink.click();
  console.log('Clicked on Purchase orders');

  // Wait for navigation
  await page.waitForTimeout(2000);

  // Click on "Create purchase order"
  const createPurchaseOrderButton = page.locator(
    'button:has-text("Create purchase order"), a:has-text("Create purchase order"), [data-testid*="create-purchase-order"]'
  );
  await createPurchaseOrderButton.waitFor({ state: 'visible', timeout: 10000 });
  await createPurchaseOrderButton.click();
  console.log('Clicked on Create purchase order');

  // Wait for navigation
  await page.waitForTimeout(5000);
}
