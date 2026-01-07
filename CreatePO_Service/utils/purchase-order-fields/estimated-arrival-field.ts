import { Page } from '@playwright/test';
import { ai } from '@zerostep/playwright';

/**
 * Fills in the Estimated arrival date field
 * Loops until the field is successfully filled (AI can only do one action at a time)
 * @param page - Playwright page object
 * @param test - Playwright test fixture from AiFixture
 * @param shipDate - The ship date in YYYY-MM-DD format
 */
export async function fillEstimatedArrivalField(page: Page, test: any, shipDate: string | undefined): Promise<void> {
  if (!shipDate) {
    console.log('No ship date provided, skipping Estimated arrival field');
    return;
  }

  console.log(`Filling Estimated arrival field with: ${shipDate}`);

  const aiArgs = { page, test };
  const maxAttempts = 10;
  let attempts = 0;
  let fieldFilled = false;

  while (!fieldFilled && attempts < maxAttempts) {
    attempts++;
    console.log(`Attempt ${attempts} to fill Estimated arrival field...`);

    try {
      // Use AI to fill the field (one action at a time)
      await ai(`Fill in the "Estimated arrival" date field with the value "${shipDate}". The format should be YYYY-MM-DD.`, aiArgs);
      await page.waitForTimeout(1000);

      // Check if the field has been filled by looking for the input value
      // Try multiple selectors to find the date input field
      const dateInputSelectors: string[] = [
        'input[placeholder*="Estimated arrival" i]',
        'input[aria-label*="Estimated arrival" i]',
        'input[type="date"]',
        'input[type="text"][value*="' + shipDate.substring(0, 4) + '"]',
      ];

      let fieldFound = false;
      for (const selector of dateInputSelectors) {
        try {
          const input = page.locator(selector).first();
          const isVisible = await input.isVisible({ timeout: 2000 }).catch(() => false);
          if (isVisible) {
            const value: string = await input.inputValue().catch(() => '');
            // Check if the value contains the date (check year and month)
            if (value.includes(shipDate.substring(0, 7)) || value === shipDate) {
              fieldFilled = true;
              fieldFound = true;
              console.log(`Estimated arrival field filled successfully with value: ${value}`);
              break;
            }
          }
        } catch (e) {
          // Continue to next selector
        }
      }

      // If we couldn't verify via input value, check if field appears filled by checking for the date text
      if (!fieldFound) {
        const dateText = await page
          .locator(`text=${shipDate}`)
          .isVisible({ timeout: 2000 })
          .catch(() => false);
        if (dateText) {
          fieldFilled = true;
          console.log('Estimated arrival field appears to be filled (found date text)');
        }
      }
    } catch (error) {
      console.log(`Attempt ${attempts} failed:`, error);
      await page.waitForTimeout(1000);
    }
  }

  if (!fieldFilled) {
    console.warn(`Failed to fill Estimated arrival field after ${maxAttempts} attempts`);
  } else {
    // Click on "Create purchase order" title to close the date selector popover
    try {
      console.log('Clicking on "Create purchase order" to close date selector popover...');

      // Wait for the h1 element to be visible first
      const createPurchaseOrderTitle = page.locator('h1:has-text("Create purchase order")').first();
      await createPurchaseOrderTitle.waitFor({ state: 'visible', timeout: 5000 });

      // Try clicking with force option in case it's covered by popover
      await createPurchaseOrderTitle.click({ timeout: 3000, force: true });
      await page.waitForTimeout(500); // Small delay to ensure popover closes
      console.log('Date selector popover closed successfully');
    } catch (error) {
      console.log('Could not click on "Create purchase order" title, trying alternative methods...');

      // Alternative: Try pressing Escape to close popover
      try {
        await page.keyboard.press('Escape');
        await page.waitForTimeout(500);
        console.log('Closed date selector popover using Escape key');
      } catch (escapeError) {
        console.log('Could not close popover with Escape key either');
        // Non-critical error, continue execution
      }
    }
  }
}
