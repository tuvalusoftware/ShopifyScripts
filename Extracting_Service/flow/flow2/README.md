# Flow 2: Product Extraction from Linesheets

## Overview

Flow 2 is an orchestration flow that extracts product information from linesheet files (PDFs, text files, etc.) using OpenAI's Responses API and optionally creates products in Shopify via DynamoServiceClient API.

## Architecture

The flow consists of 5 sequential steps, each implemented as a separate module:

1. **Step 1: Initialize** (`step1_init.py`)
2. **Step 2: Collect Files** (`step2_collect_files.py`)
3. **Step 3: Process Files** (`step3_process_file_with_llm.py`)
4. **Step 4: Create Products** (`step4_create_products_to_dynamo.py`)
5. **Step 6: Delete Files** (`step6_delete_files.py`)

The main orchestration file (`flow2.py`) coordinates these steps and manages the execution flow.

## Features

- Batch processing of multiple files from a directory
- File filtering by extension and size
- Recursive directory scanning option
- OpenAI file upload and Responses API integration
- Automatic product extraction from model responses
- Sender information enrichment based on filename prefix mapping
- Optional product creation via DynamoServiceClient API
- Optional file deletion after successful processing
- Comprehensive metadata tracking and logging
- Per-file processing results and statistics

## Data Flow

### Input Data

- **Directory path**: Contains files to process (linesheets)
- **Prompt file**: Text file containing the extraction prompt for OpenAI model
- **Configuration parameters**: Model name, file filters, output settings

### Processing Flow

1. **Initialization**: Sets up OpenAI client, DynamoServiceClient (optional), loads prompt, initializes DirectoryManager
2. **File Collection**: Scans input directory, filters files by extension and size, collects file metadata
3. **File Processing**: For each file:
   - Calculates SHA256 hash
   - Uploads file to OpenAI
   - Calls Responses API with prompt and file
   - Parses JSON products from response
   - Enriches products with sender information (if sender mapping file provided)
4. **Product Creation**: For each extracted product:
   - Converts product data to properties format
   - Calls DynamoServiceClient API to create product
   - Tracks success/error counts
5. **File Deletion**: Optionally deletes successfully processed files if deletion is enabled

### Output Data

- **Run directory**: Created under base output directory (from `OUTPUT_DIR` env var or `--out_dir` argument)
- **Responses directory**: Subdirectory for response files (currently not written to disk)
- **Processing results**: Stored in memory and logged, including:
  - File processing statistics
  - Product extraction and creation counts
  - Per-file detailed results

## Data Interface

### Step 1 Output (`step1_init`)

- `openai_client`: OpenAI client instance
- `dynamo_client`: DynamoServiceClient instance (optional, can be None)
- `prompt`: Prompt text string
- `prompt_path`: Path to prompt file

Note: `run_dir` and `responses_dir` are managed by `DirectoryManager` singleton, not returned by step1.

### Step 2 Output (`step2_collect_files`)

- `files`: List of file dictionaries, each containing:
  - `path`: Full file path
  - `name`: File name
  - `size_bytes`: File size in bytes
- `total_found`: Total files found before filtering
- `total_collected`: Total files collected after filtering

### Step 3 Output (`step3_process_file_with_llm`)

Per-file result dictionary:

- `input_path`: Input file path
- `input_name`: Input file name
- `input_size_bytes`: File size
- `input_sha256`: SHA256 hash of file
- `uploaded_file_id`: OpenAI file ID
- `status`: Processing status (`pending`, `ok`, `error`, `skipped`)
- `started_at_utc`: Processing start time (ISO format)
- `finished_at_utc`: Processing end time (ISO format)
- `duration_seconds`: Processing duration
- `response_path`: Path to response file (currently None, not written to disk)
- `products_extracted`: Number of products extracted
- `products`: List of extracted product dictionaries (enriched with sender info if mapping provided)
- `products_created_success`: Number of products successfully created (added by step4)
- `products_created_error`: Number of products failed to create (added by step4)
- `product_creation_errors`: List of error messages (added by step4)
- `error`: Error message if processing failed

### Step 4 Output (`step4_create_products_to_dynamo`)

- `status`: Step status (`pending`, `ok`, `skipped`, `error`)
- `started_at_utc`: Step start time (ISO format)
- `finished_at_utc`: Step end time (ISO format)
- `duration_seconds`: Step duration
- `total_products_processed`: Total products processed
- `total_products_created_success`: Successfully created products count
- `total_products_created_error`: Failed creation count
- `file_results_updated`: Updated file results with creation statistics:
  - `products_created_success`: Per-file success count
  - `products_created_error`: Per-file error count
  - `product_creation_errors`: List of error messages
- `error`: Error message if step failed

### Step 6 Output (`step6_delete_files`)

- `status`: Step status (`pending`, `ok`, `skipped`, `error`)
- `deleted_count`: Number of files successfully deleted
- `failed_delete_count`: Number of files that failed to delete
- `skipped_count`: Number of files skipped (not found or not eligible)
- `deleted_files`: List of deleted file information (name, path)
- `failed_files`: List of failed deletion information (name, path, error)
- `error`: Error message if step failed

## File Structure

```
flow2/
├── flow2.py                        # Main orchestration file
├── step1_init.py                   # Initialize clients and directories
├── step2_collect_files.py          # Collect files from directory
├── step3_process_file_with_llm.py # Process single file (upload, extract, enrich)
├── step4_create_products_to_dynamo.py # Create products via Dynamo API
├── step6_delete_files.py           # Delete processed files (optional)
└── README.md                       # This file
```

## Dependencies

- OpenAI Python SDK: For file uploads and Responses API
- DynamoServiceClient: For product creation (optional, from `domain/DynamoServiceClient`)
- DirectoryManager: For directory management (from `flow/utils/directory_manager`)
- Logger: For logging (from `flow/utils/logger`)
- Standard library: `pathlib`, `json`, `hashlib`, `datetime`, `time`, `os`, `re`

## Environment Variables

- `OPENAI_API_KEY`: Required for OpenAI API access
- `MAX_BYTES`: Optional, default 20000000 (20MB) for maximum file size
- `OUTPUT_DIR`: Optional, base output directory path (default: current directory)
- `DELETE_FILE_AFTER_PROCESS`: Optional, enable file deletion after successful processing (default: `false`)

## Usage

The flow is executed via the main `flow2.py` script with command-line arguments:

- `--attachment_dir`: Directory containing files to process (required)
- `--prompt_file`: Path to prompt text file (required)
- `--model`: OpenAI model name (default: `gpt-4.1-mini`)
- `--ext`: File extensions to include (e.g., `.pdf .txt`) - can specify multiple
- `--recursive`: Enable recursive directory scanning
- `--max_files`: Maximum files to process (default: 50)
- `--max_bytes`: Maximum file size in bytes (default: 20000000, or from `MAX_BYTES` env var)
- `--max_output_tokens`: Maximum output tokens for model (default: 20000)
- `--out_dir`: Output directory (default: `./outputs`, overridden by `OUTPUT_DIR` env var)
- `--no_run_subdir`: Write directly to output directory (no `run_*` subdirectory)
- `--response_ext`: Response file extension (default: `.txt`)
- `--upload_purpose`: OpenAI upload purpose (default: `assistants`)
- `--sender_mapping_file`: Optional path to sender mapping JSON file (maps filename prefix to sender_email and sender_name)

## Output Structure

```
outputs/
└── run_YYYYMMDD_HHMMSS/
    └── responses/
        └── (directory created, currently unused)
```

Note: Response files are not currently written to disk. The `responses/` directory is created but remains empty. Processing results are logged and stored in memory.

## Error Handling

- Step failures are tracked in result dictionaries with `success` boolean and `error` message
- File processing errors are captured per-file without stopping the entire flow
- DynamoServiceClient unavailability is handled gracefully (extraction continues, creation is skipped)
- File deletion failures are logged but do not stop the flow
- Exit codes: 0 for success, 1 for errors, 2 for initialization failures

## Sender Information Enrichment

If `--sender_mapping_file` is provided, products are enriched with sender information based on filename prefix:

- Filename format: `{prefix}_{idx:02d}_{filename}` (e.g., `eml0001_01_file.pdf`)
- Prefix is extracted and used to lookup sender_email and sender_name from mapping file
- Mapping file format: `{"prefix": {"sender_email": "...", "sender_name": "..."}}`
- Enriched fields are added to each product: `sender_email` and `sender_name`

## Relationship to Other Flows

- **Flow 1**: Processes EML files from S3, extracts products, writes to local files
- **Flow 2**: Processes local files (linesheets), extracts products, optionally creates products via Dynamo API

Flow 2 can be used independently or as a follow-up to Flow 1 to process extracted files and create products in Shopify.
