import { Page } from '@playwright/test';
import { ai } from '@zerostep/playwright';

/**
 * Fills in the Reference number field
 * Loops until the field is successfully filled (AI can only do one action at a time)
 * @param page - Playwright page object
 * @param test - Playwright test fixture from AiFixture
 * @param referenceNumber - The reference/order confirmation number
 */
export async function fillReferenceNumberField(page: Page, test: any, referenceNumber: string | undefined): Promise<void> {
  if (!referenceNumber) {
    console.log('No reference number provided, skipping Reference number field');
    return;
  }

  console.log(`Filling Reference number field with: ${referenceNumber}`);

  const aiArgs = { page, test };
  const maxAttempts = 10;
  let attempts = 0;
  let fieldFilled = false;

  while (!fieldFilled && attempts < maxAttempts) {
    attempts++;
    console.log(`Attempt ${attempts} to fill Reference number field...`);

    try {
      // Use AI to fill the field (one action at a time)
      await ai(`Fill in the "Reference number" field with the value "${referenceNumber}".`, aiArgs);
      await page.waitForTimeout(1000);

      // Check if the field has been filled by looking for the input value
      // Try multiple selectors to find the reference number input field
      const inputSelectors: string[] = [
        'input[name="referenceNumber"]', // Most specific selector based on actual HTML
        'input[name*="reference" i]',
        'input[placeholder*="Reference number" i]',
        'input[aria-label*="Reference number" i]',
        'input.Polaris-TextField__Input[type="text"]',
      ];

      let fieldFound = false;
      for (const selector of inputSelectors) {
        try {
          const input = page.locator(selector).first();
          const isVisible = await input.isVisible({ timeout: 2000 }).catch(() => false);
          if (isVisible) {
            const value: string = await input.inputValue().catch(() => '');
            // Check if the value matches the reference number (trim whitespace for comparison)
            const trimmedValue = value.trim();
            if (trimmedValue === referenceNumber || trimmedValue.includes(referenceNumber)) {
              fieldFilled = true;
              fieldFound = true;
              console.log(`Reference number field filled successfully with value: ${value}`);
              break;
            }
          }
        } catch (e) {
          // Continue to next selector
        }
      }

      // If we couldn't verify via input value, check if field appears filled by checking for the reference number text
      if (!fieldFound) {
        const referenceText = await page
          .locator(`text=${referenceNumber}`)
          .isVisible({ timeout: 2000 })
          .catch(() => false);
        if (referenceText) {
          fieldFilled = true;
          console.log('Reference number field appears to be filled (found reference number text)');
        }
      }
    } catch (error) {
      console.log(`Attempt ${attempts} failed:`, error);
      await page.waitForTimeout(1000);
    }
  }

  if (!fieldFilled) {
    console.warn(`Failed to fill Reference number field after ${maxAttempts} attempts`);
  }
}
