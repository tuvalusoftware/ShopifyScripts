# Shopify Automation with ZeroStep

Minimal setup project for using ZeroStep AI with Playwright tests.

## Setup

1. **Install dependencies:**
   ```bash
   npm install
   ```

2. **Configure ZeroStep token:**
   
   Option A - Environment variable:
   ```bash
   export ZEROSTEP_TOKEN="<your token here>"
   ```
   
   Option B - Config file:
   Create a `zerostep.config.json` file in the root:
   ```json
   {
     "TOKEN": "<your token here>"
   }
   ```
   
   Get your token from [https://app.zerostep.com](https://app.zerostep.com)

3. **Run tests:**
   ```bash
   npm test              # Run tests headless
   npm run test:ui       # Run tests with UI mode
   npm run test:headed   # Run tests in headed browser
   ```

## Usage

The `ai()` function accepts natural language prompts:

```typescript
import { test } from '@playwright/test';
import { ai } from '@zerostep/playwright';

test('example', async ({ page }) => {
  await page.goto('https://example.com');
  const aiArgs = { page, test };
  
  // Actions
  await ai('Click the login button', aiArgs);
  
  // Queries
  const text = await ai('Get the page title', aiArgs);
  
  // Assertions
  const hasButton = await ai('Is there a submit button?', aiArgs);
});
```

## Notes

- ZeroStep only supports Chromium browsers
- Write prompts in complete English sentences
- Put quotes around exact text: `Click on the "Login" button`
- Each prompt should contain one distinct action, query, or assertion

