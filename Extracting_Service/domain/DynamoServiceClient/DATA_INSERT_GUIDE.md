# Data Insert Endpoint Guide

## Overview

The `/data/insert` endpoint allows you to import JSON data files into DynamoDB. This endpoint accepts JSON files in various formats and automatically processes them for storage.

## Endpoint Details

**URL:** `POST /data/insert`

**Content-Type:** `multipart/form-data`

**Request:** File upload (JSON file)

**Response:** Import summary with success status and statistics

## Supported JSON Formats

The endpoint supports multiple JSON file formats:

### Format 1: Merged Format

Files containing a `results` array with nested data:

```json
{
  "results": [
    {
      "pdf": "document.pdf",
      "page": 1,
      "column": 1,
      "part": 1,
      "result": {
        "products": [
          {
            "product_name": "Item Name",
            "style_number": "SKU-001",
            ...
          }
        ]
      }
    }
  ]
}
```

### Format 2: Direct Products Format

Files containing a direct `products` array:

```json
{
  "products": [
    {
      "product_name": "Item Name",
      "style_number": "SKU-001",
      ...
    }
  ]
}
```

### Format 3: Page-specific Format

Files named with pattern `page_{number}_col_{number}_part_{number}.json`:

```json
{
  "products": [
    {
      "product_name": "Item Name",
      ...
    }
  ]
}
```

## Request Example

### Using cURL

```bash
curl -X POST "http://localhost:8080/data/insert" \
  -F "file=@your-data-file.json"
```

### Using Python requests

```python
import requests

url = "http://localhost:8080/data/insert"
files = {"file": open("your-data-file.json", "rb")}

response = requests.post(url, files=files)
print(response.json())
```

### Using JavaScript/Node.js

```javascript
const FormData = require('form-data');
const fs = require('fs');
const axios = require('axios');

const form = new FormData();
form.append('file', fs.createReadStream('your-data-file.json'));

axios
  .post('http://localhost:8080/data/insert', form, {
    headers: form.getHeaders(),
  })
  .then((response) => console.log(response.data))
  .catch((error) => console.error(error));
```

## Response Format

The endpoint returns an `ImportResponse` object with the following structure:

```json
{
  "success": true,
  "message": "Imported 150/150 items",
  "total": 150,
  "imported": 150,
  "failed": 0,
  "errors": [],
  "sample_products": [
    {
      "id": "uuid-here",
      "product_name": "Sample Item",
      "style_number": "SKU-001"
    }
  ]
}
```

### Response Fields

- **success** (boolean): Whether all items were imported successfully
- **message** (string): Human-readable summary message
- **total** (integer): Total number of items found in the file
- **imported** (integer): Number of items successfully imported
- **failed** (integer): Number of items that failed to import
- **errors** (array): List of error objects (limited to first 10 errors)
  - Each error contains:
    - `index`: Position of the failed item
    - `error`: Error message
    - `product_name`: Name of the item that failed (if available)
- **sample_products** (array): First 5 successfully imported items (for verification)

## Error Responses

### Invalid File Type

**Status Code:** 400

```json
{
  "detail": "Only JSON files are accepted"
}
```

### Invalid JSON Format

**Status Code:** 400

```json
{
  "detail": "Invalid JSON format: [error details]"
}
```

### File Read Error

**Status Code:** 400

```json
{
  "detail": "Error reading file: [error details]"
}
```

### No Data Found

**Status Code:** 200 (but success: false)

```json
{
  "success": false,
  "message": "No products found in JSON. Expected 'results' or 'products' array.",
  "total": 0,
  "imported": 0,
  "failed": 0,
  "errors": []
}
```

## Data Processing

The endpoint automatically:

1. Validates the file is a JSON file
2. Parses the JSON content
3. Detects the file format (merged, direct products, or page-specific)
4. Extracts all data items from the file
5. Normalizes and serializes each item
6. Stores each item in DynamoDB with a unique ID
7. Returns a summary of the import operation

## File Size Considerations

- The endpoint supports large files (1000+ lines)
- Files are read entirely into memory before processing
- For very large files, consider splitting into smaller batches

## Best Practices

1. **Validate JSON before upload**: Ensure your JSON file is valid before sending
2. **Check response**: Always check the `success` field and review `errors` array
3. **Handle partial failures**: Even if `success` is false, some items may have been imported (check `imported` count)
4. **Use sample_products**: Review the `sample_products` array to verify data was imported correctly
5. **File naming**: Use descriptive filenames to help track imports

## Example Workflow

1. Prepare your JSON file in one of the supported formats
2. Make a POST request to `/data/insert` with the file
3. Check the response for `success` status
4. Review `sample_products` to verify data structure
5. If errors occurred, check the `errors` array for details
6. Query DynamoDB to confirm data was stored correctly

## Related Files

- Endpoint implementation: `app/presentation/api/routes/import_routes.py`
- Import service: `app/application/services/import_service.py`
- Response schema: `app/presentation/api/schemas/import_schemas.py`
- Database connection: `app/infrastructure/database/dynamodb.py`
