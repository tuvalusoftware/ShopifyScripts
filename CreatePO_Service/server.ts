import express from 'express';
import { writeFileSync, mkdirSync, existsSync, unlinkSync } from 'fs';
import { execSync } from 'child_process';
import { join } from 'path';

const app = express();
const PORT = process.env.PORT || 3000;
const TEMP_DIR = join(process.cwd(), 'temp');

// Ensure temp directory exists
if (!existsSync(TEMP_DIR)) {
  mkdirSync(TEMP_DIR, { recursive: true });
}

// Middleware
app.use(express.json());

// Health check endpoint
app.get('/health', (req, res) => {
  res.json({ status: 'ok', timestamp: new Date().toISOString() });
});

// Process order endpoint
app.post('/api/process-order', async (req, res) => {
  let filePath: string | null = null;

  try {
    // Validate request body
    const order = req.body;

    if (!order || typeof order !== 'object') {
      return res.status(400).json({
        success: false,
        error: 'Invalid request body: expected JSON object',
      });
    }

    // Validate required fields based on mockData structure
    const requiredFields = ['orderConfirmationNumber', 'brandName'];
    const missingFields = requiredFields.filter((field) => !order[field]);

    if (missingFields.length > 0) {
      return res.status(400).json({
        success: false,
        error: `Missing required fields: ${missingFields.join(', ')}`,
      });
    }

    // Generate unique temp file path
    const timestamp = Date.now();
    const fileName = `order-${timestamp}.json`;
    filePath = join(TEMP_DIR, fileName);

    // Write order data to temp file
    try {
      writeFileSync(filePath, JSON.stringify(order, null, 2), 'utf-8');
    } catch (fileError) {
      return res.status(500).json({
        success: false,
        error: `Failed to write temp file: ${fileError instanceof Error ? fileError.message : 'Unknown error'}`,
      });
    }

    // Execute Playwright test with ORDER_DATA_PATH environment variable
    let testOutput = '';
    let testSuccess = false;

    try {
      // Set ORDER_DATA_PATH and run the test in headless mode
      const env = {
        ...process.env,
        ORDER_DATA_PATH: filePath,
      };

      testOutput = execSync('npx playwright test tests/shopify.spec.ts', {
        encoding: 'utf-8',
        env,
        stdio: 'pipe',
        maxBuffer: 10 * 1024 * 1024, // 10MB buffer for large outputs
      }) as string;

      testSuccess = true;
    } catch (testError: any) {
      // Capture test output even on failure
      // execSync error contains stdout and stderr properties
      const stdout = testError.stdout || '';
      const stderr = testError.stderr || '';
      testOutput = stdout + (stderr ? '\n' + stderr : '') || testError.message || 'Test execution failed';
      testSuccess = false;
    }

    // Return response
    if (testSuccess) {
      res.status(200).json({
        success: true,
        message: 'Order processed successfully',
        orderNumber: order.orderConfirmationNumber,
        filePath: filePath,
        testOutput: testOutput,
      });
    } else {
      res.status(500).json({
        success: false,
        error: 'Test execution failed',
        orderNumber: order.orderConfirmationNumber,
        filePath: filePath,
        testOutput: testOutput,
      });
    }
  } catch (error) {
    res.status(500).json({
      success: false,
      error: error instanceof Error ? error.message : 'Unknown error occurred',
    });
  } finally {
    // Clean up temp file after processing
    if (filePath && existsSync(filePath)) {
      try {
        unlinkSync(filePath);
        console.log(`Cleaned up temp file: ${filePath}`);
      } catch (cleanupError) {
        console.error(`Failed to delete temp file ${filePath}:`, cleanupError);
      }
    }
  }
});

// Start server
app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
  console.log(`Health check: http://localhost:${PORT}/health`);
  console.log(`Process order: POST http://localhost:${PORT}/api/process-order`);
});
