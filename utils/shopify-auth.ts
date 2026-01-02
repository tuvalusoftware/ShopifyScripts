import { Page } from '@playwright/test';

/**
 * Authenticates with Shopify using email and password
 * @param page - Playwright page object
 * @param username - Email/username for login
 * @param password - Password for login
 * @throws Error if authentication fails
 */
export async function authenticateShopify(page: Page, username: string, password: string): Promise<void> {
  // Navigate to shopify page
  await page.goto('https://www.shopify.com/login?ui_locales=en', { waitUntil: 'domcontentloaded' });

  // Wait for page to load
  await page.waitForTimeout(3000);

  // Enter email from the USERNAME env variable
  const emailInput = page.locator('input[type="email"]');
  await emailInput.waitFor({ state: 'visible', timeout: 10000 });
  await emailInput.fill(username);
  await page.waitForTimeout(1000);

  // Click continue with email button
  const continueWithEmailButton = page.locator('button:has-text("Continue with email")');
  await continueWithEmailButton.waitFor({ state: 'visible' });
  await continueWithEmailButton.click();

  // Wait for navigation
  await page.waitForTimeout(5000);

  // Click on the link "Log in using a different method"
  const logInUsingDifferentMethodButton = page.locator('a:has-text("Log in using a different method")');
  await logInUsingDifferentMethodButton.waitFor({ state: 'visible', timeout: 10000 });
  await logInUsingDifferentMethodButton.click();

  // Wait a bit
  await page.waitForTimeout(2000);

  // Click on the link "Continue with password"
  const continueWithPasswordButton = page.locator('a:has-text("Continue with password")');
  await continueWithPasswordButton.waitFor({ state: 'visible', timeout: 10000 });
  await continueWithPasswordButton.click();

  // Wait for password input to appear
  await page.waitForTimeout(2000);

  // Locate the password input and wait for it
  const passwordInput = page.locator('input[type="password"]');
  await passwordInput.waitFor({ state: 'visible', timeout: 10000 });
  // Type the password from the PASS env variable
  await passwordInput.fill(password);
  // Hit the button "Log in"
  const logInButton = page.locator('button:has-text("Log in")');
  await logInButton.click();
  console.log('Shopify authentication successful');
}
