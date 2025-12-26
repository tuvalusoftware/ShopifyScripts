import { test } from '../fixtures/test';
import { ai } from '@zerostep/playwright';

test('shopify automation', async ({ page }) => {
  // Use environment variables for username and password
  const username = process.env.USERNAME;
  const password = process.env.PASS;

  if (!username || !password) {
    throw new Error('USERNAME and PASS environment variables must be set');
  }

  await page.goto('https://www.shopify.com/login?ui_locales=en');

  const aiArgs = { page, test };

  // Call AI 10 times, each doing a single action
  for (let i = 0; i < 10; i++) {
    try {
      const result = await ai(
        `The target is to login to Shopify with username "${username}" and password "${password}". Don't choose the option login with passkey but choose login with different method.`,
        aiArgs
      );
      console.log(result);
    } catch (e) {
      console.log(e);
    }
    // Small delay between actions
    await page.waitForTimeout(3000);
  }

  // Wait for navigation after login
  await page.waitForTimeout(2000);

  // Verify login was successful by checking for the Products sidebar
  const isLoggedIn = await page
    .locator('nav[aria-label="Sidebar"] >> text=Products')
    .first()
    .isVisible({ timeout: 10000 })
    .catch(() => false);

  if (!isLoggedIn) {
    throw new Error('Failed to login successfully');
  }

  console.log('Successfully logged in with AI');
});
