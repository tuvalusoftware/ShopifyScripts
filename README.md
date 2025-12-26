# Shopify Automation

A Shopify automation project using Playwright and ZeroStep AI to automatically fill Purchase Order forms on Shopify Admin.

## System Requirements

- Node.js (version 18 or higher)
- npm or yarn
- Valid Shopify Admin account

## Installation

1. Clone the repository:

```bash
git clone <repository-url>
cd shopify-automation
```

2. Install dependencies:

```bash
npm install
```

3. Install Playwright browsers:

```bash
npx playwright install
```

## Environment Variables Configuration

The project uses a `.env` file to store environment variables. Create a `.env` file in the project root directory with the following content:

```env
USERNAME=your-shopify-email@example.com
PASS=your-shopify-password
ZEROSTEP_TOKEN=your-zerostep-api-token
```

### Required Environment Variables:

- **USERNAME**: Your Shopify login email
- **PASS**: Your Shopify login password
- **ZEROSTEP_TOKEN**: Your ZeroStep API token for AI-powered automation

### Security Notes:

- **DO NOT** commit the `.env` file to git (this file should be added to `.gitignore`)
- Keep your login credentials secure
- Only use test accounts in development environment

## How to Run

### Run specific Shopify test:

```bash
npm run test:shopify
```

## Project Structure

```
shopify-automation/
├── tests/                    # Test files
│   └── shopify.spec.ts      # Main test for Shopify automation
├── utils/                    # Utility functions
│   ├── shopify-auth.ts      # Authentication handling
│   ├── shopify-navigation.ts # Navigation helpers
│   ├── fill-purchase-order.ts # Form filling logic
│   └── purchase-order-fields/ # Field handlers
├── fixtures/                 # Playwright fixtures
│   └── test.ts              # Custom test fixture with AI
├── mockData.json            # Sample test data
├── auth-state.json          # Session storage (auto-generated)
├── playwright.config.ts     # Playwright configuration
└── package.json             # Dependencies and scripts
```

## Features

- **Auto login**: Uses credentials from environment variables
- **Session persistence**: Automatically saves login state to avoid re-authentication
- **Auto form filling**: Automatically fills Purchase Order form with data from `mockData.json`
- **AI-powered**: Uses ZeroStep AI to automatically select products

## Troubleshooting

### Error "USERNAME and PASS environment variables must be set"

- Make sure you've created the `.env` file with all required environment variables
- Check the variable names: `USERNAME` and `PASS` (exactly as shown)

### Test timeout

- Default timeout is 10 minutes (600000ms)
- If tests timeout, you can increase the value in `playwright.config.ts`

### Browser not installed

- Run: `npx playwright install chromium`

## Notes

- The `auth-state.json` file will be automatically created after the first run to save the session
- Tests will process the first 3 orders from `mockData.json`
- Make sure you have access to Shopify Admin before running tests
