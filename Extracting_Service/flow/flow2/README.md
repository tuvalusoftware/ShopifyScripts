# Flow 2: Product Extraction from Linesheets

## Overview

Flow 2 is an orchestration flow that extracts product information from linesheet files (PDFs, text files, etc.) using OpenAI's Responses API and optionally creates products in Shopify via DynamoServiceClient API.

## Architecture

The flow consists of 5 sequential steps, each implemented as a separate module:

1. **Step 1: Initialize** (`step1_init.py`)
2. **Step 2: Collect Files** (`step2_collect_files.py`)
3. **Step 3: Process Files** (`step3_process_file.py`)
4. **Step 4: Create Products** (`step4_create_products.py`)
5. **Step 5: Write Metadata** (`step5_write_metadata.py`)

The main orchestration file (`flow2.py`) coordinates these steps and manages the execution flow.

## Features

- Batch processing of multiple files from a directory
- File filtering by extension and size
- Recursive directory scanning option
- OpenAI file upload and Responses API integration
- Automatic product extraction from model responses
- Optional product creation via DynamoServiceClient API
- Comprehensive metadata tracking and logging
- Per-file processing results and statistics

## Data Flow

### Input Data

- **Directory path**: Contains files to process (linesheets)
- **Prompt file**: Text file containing the extraction prompt for OpenAI model
- **Configuration parameters**: Model name, file filters, output settings

### Processing Flow

1. **Initialization**: Sets up OpenAI client, DynamoServiceClient (optional), loads prompt, creates output directories
2. **File Collection**: Scans input directory, filters files by extension and size, collects file metadata
3. **File Processing**: For each file:
   - Calculates SHA256 hash
   - Uploads file to OpenAI
   - Calls Responses API with prompt and file
   - Parses JSON products from response
   - Writes response text to disk
4. **Product Creation**: For each extracted product:
   - Converts product data to properties format
   - Calls DynamoServiceClient API to create product
   - Tracks success/error counts
5. **Metadata Writing**: Writes comprehensive run metadata JSON file

### Output Data

- **Response files**: One per processed file, stored in `responses/` subdirectory
- **Run metadata**: JSON file containing:
  - Run timing information
  - Configuration parameters
  - File processing statistics
  - Product extraction and creation counts
  - Per-file detailed results

## Data Interface

### Step 1 Output (`step1_init`)

- `openai_client`: OpenAI client instance
- `dynamo_client`: DynamoServiceClient instance (optional, can be None)
- `prompt`: Prompt text string
- `prompt_path`: Path to prompt file
- `run_dir`: Run output directory path
- `responses_dir`: Responses subdirectory path

### Step 2 Output (`step2_collect_files`)

- `files`: List of file dictionaries, each containing:
  - `path`: Full file path
  - `name`: File name
  - `size_bytes`: File size in bytes
- `total_found`: Total files found before filtering
- `total_collected`: Total files collected after filtering

### Step 3 Output (`step3_process_file`)

Per-file result dictionary:

- `input_path`: Input file path
- `input_name`: Input file name
- `input_size_bytes`: File size
- `input_sha256`: SHA256 hash of file
- `uploaded_file_id`: OpenAI file ID
- `status`: Processing status (`ok`, `error`, `skipped`)
- `started_at_utc`: Processing start time (ISO format)
- `finished_at_utc`: Processing end time (ISO format)
- `duration_seconds`: Processing duration
- `response_path`: Path to written response file
- `products_extracted`: Number of products extracted
- `products`: List of extracted product dictionaries
- `error`: Error message if processing failed

### Step 4 Output (`step4_create_products`)

- `total_products_processed`: Total products processed
- `total_products_created_success`: Successfully created products count
- `total_products_created_error`: Failed creation count
- `file_results_updated`: Updated file results with creation statistics:
  - `products_created_success`: Per-file success count
  - `products_created_error`: Per-file error count
  - `product_creation_errors`: List of error messages

### Step 5 Output (`step5_write_metadata`)

- `metadata_path`: Path to written metadata JSON file

### Run Metadata JSON Structure

- Run timing: `run_started_at_utc`, `run_finished_at_utc`, `duration_seconds`
- Configuration: `model`, `prompt_file`, `input_dir`, `recursive`, `exts`, `max_files`, `max_bytes`, `max_output_tokens`, `out_dir`, `response_ext`, `upload_purpose`
- Statistics: `files_total_seen`, `files_uploaded`, `files_ok`, `files_skipped`, `files_error`
- Product statistics: `total_products_extracted`, `total_products_created_success`, `total_products_created_error`
- Detailed results: `file_results` array with per-file processing details

## File Structure

```
flow2/
├── flow2.py                 # Main orchestration file
├── step1_init.py            # Initialize clients and directories
├── step2_collect_files.py   # Collect files from directory
├── step3_process_file.py    # Process single file (upload, extract)
├── step4_create_products.py # Create products via Dynamo API
├── step5_write_metadata.py  # Write run metadata JSON
└── README.md                # This file
```

## Dependencies

- OpenAI Python SDK: For file uploads and Responses API
- DynamoServiceClient: For product creation (optional, from `domain/DynamoServiceClient`)
- Standard library: `pathlib`, `json`, `hashlib`, `datetime`, `time`

## Environment Variables

- `OPENAI_API_KEY`: Required for OpenAI API access
- `MAX_BYTES`: Optional, default 20000000 (20MB) for maximum file size

## Usage

The flow is executed via the main `flow2.py` script with command-line arguments:

- `--dir`: Directory containing files to process (required)
- `--prompt_file`: Path to prompt text file (required)
- `--model`: OpenAI model name (default: `gpt-4.1-mini`)
- `--ext`: File extensions to include (e.g., `.pdf .txt`)
- `--recursive`: Enable recursive directory scanning
- `--max_files`: Maximum files to process (default: 50)
- `--max_bytes`: Maximum file size in bytes (default: 20000000)
- `--max_output_tokens`: Maximum output tokens for model (default: 20000)
- `--out_dir`: Output directory (default: `./outputs`)
- `--no_run_subdir`: Write directly to output directory (no `run_*` subdirectory)
- `--response_ext`: Response file extension (default: `.txt`)
- `--upload_purpose`: OpenAI upload purpose (default: `assistants`)

## Output Structure

```
outputs/
└── run_YYYYMMDD_HHMMSS/
    ├── responses/
    │   ├── filename1__hash123.txt
    │   ├── filename2__hash456.txt
    │   └── ...
    └── run-metadata.json
```

## Error Handling

- Step failures are tracked in result dictionaries with `success` boolean and `error` message
- File processing errors are captured per-file without stopping the entire flow
- DynamoServiceClient unavailability is handled gracefully (extraction continues, creation is skipped)
- Exit codes: 0 for success, 1 for errors, 2 for initialization failures

## Relationship to Other Flows

- **Flow 1**: Processes EML files from S3, extracts products, writes to local files
- **Flow 2**: Processes local files (linesheets), extracts products, optionally creates products via Dynamo API

Flow 2 can be used independently or as a follow-up to Flow 1 to process extracted files and create products in Shopify.
