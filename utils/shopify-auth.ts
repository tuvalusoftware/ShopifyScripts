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
  await page.goto('https://www.shopify.com/login?ui_locales=en');

  // Loop until we successfully reach the password page
  const maxAttempts = 10;
  let attempts = 0;
  let passwordPageReached = false;

  while (!passwordPageReached && attempts < maxAttempts) {
    attempts++;
    console.log(`Attempt ${attempts} to reach password page...`);

    try {
      // Check and handle captcha if present (using AI)
      await page.waitForTimeout(5000);
    } catch (e) {
      console.log(e);
      // No captcha refresh needed
    }

    // Enter email from the USERNAME env variable
    const emailInput = page.locator('input[type="email"]');
    await emailInput.waitFor({ state: 'visible' });
    await emailInput.fill(username);
    await page.waitForTimeout(1000);

    // Click continue with email button manually
    const continueWithEmailButton = page.locator('button:has-text("Continue with email")');
    await continueWithEmailButton.waitFor({ state: 'visible' });
    await continueWithEmailButton.click();

    // Wait a bit for navigation
    await page.waitForTimeout(5000);

    // Click on the link "Log in using a different method"
    const logInUsingDifferentMethodButton = page.locator('a:has-text("Log in using a different method")');
    await logInUsingDifferentMethodButton.waitFor({ state: 'visible' });
    await logInUsingDifferentMethodButton.click();

    // Click on the link "Continue with password"
    const continueWithPasswordButton = page.locator('a:has-text("Continue with password")');
    await continueWithPasswordButton.waitFor({ state: 'visible' });
    await continueWithPasswordButton.click();

    // Check if we've reached the password page
    const passwordInput = page.locator('input[type="password"]');
    const isPasswordPageVisible = await passwordInput.isVisible({ timeout: 3000 }).catch(() => false);

    if (isPasswordPageVisible) {
      passwordPageReached = true;
      console.log('Successfully reached password page!');
    } else {
      console.log('Still on email page, retrying...');
      await page.waitForTimeout(1000);
    }
  }

  if (!passwordPageReached) {
    throw new Error(`Failed to reach password page after ${maxAttempts} attempts`);
  }

  // Locate the password input
  const passwordInput = await page.locator('input[type="password"]');
  // Type the password from the PASS env variable
  await passwordInput.fill(password);
  // Hit the button "Log in"
  const logInButton = await page.locator('button:has-text("Log in")');
  await logInButton.click();
  console.log('Shopify authentication successful');
}
