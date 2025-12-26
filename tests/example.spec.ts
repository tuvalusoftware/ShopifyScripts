import { test } from '@playwright/test';
import { ai } from '@zerostep/playwright';

test('zerostep example', async ({ page }) => {
  await page.goto('https://zerostep.com/');

  // An object with page and test must be passed into every call
  const aiArgs = { page, test };

  // Get text from the page
  const headerText = await ai('Get the header text', aiArgs);
  console.log('Header text:', headerText);

  // Navigate to another page
  await page.goto('https://google.com/');

  // Type text using AI
  await ai(`Type "${headerText}" in the search box`, aiArgs);

  // Press enter
  await ai('Press enter', aiArgs);

  // Wait for results
  await page.waitForTimeout(2000);
});
