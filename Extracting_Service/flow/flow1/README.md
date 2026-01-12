# Flow 1: S3 EML Processing and Product Extraction

## Overview

Flow 1 is an orchestration flow that processes email files (EML format) stored in AWS S3, extracts email metadata and attachments, and optionally triggers product extraction from attachments using Flow 2.

## Architecture

The flow consists of 7 sequential steps, each implemented as a separate module:

1. **Step 1: Initialize S3** (`step1_init_s3.py`)
2. **Step 2: List EML Files** (`step2_list_eml.py`)
3. **Step 3: Download EML** (`step3_download_eml.py`)
4. **Step 4: Parse EML** (`step4_parse_eml.py`)
5. **Step 5: Delete EML** (`step5_delete_eml.py`)
6. **Step 6: Extract Products** (`step6_extract_products.py`)
7. **Step 7: Write Output** (`step7_write_output.py`)

The main orchestration file (`flow1.py`) coordinates these steps and manages the execution flow. Steps 3-5 are executed per file in a loop, while steps 1, 2, 7, and 6 are executed once per run. Note: Step 7 (Write Output) executes before Step 6 (Extract Products).

## Features

- S3 bucket scanning for EML files
- Batch processing of multiple EML files
- Email parsing with attachment extraction
- Attachment saving with prefix-based naming
- Optional S3 file deletion after successful processing
- Integration with Flow 2 for product extraction from attachments
- Sender mapping file generation for product extraction
- Comprehensive JSON output with processing statistics
- Per-file error handling without stopping entire flow

## Data Flow

### Input Data

- **S3 bucket**: AWS S3 bucket containing EML files
- **S3 prefix**: Prefix path within bucket to search for EML files
- **AWS region**: AWS region for S3 access
- **Output directory**: Base directory for all output files
- **Extraction prompt file**: Optional prompt file for Flow 2 product extraction
- **Configuration flags**: Enable/disable extraction, enable/disable S3 deletion

### Processing Flow

1. **S3 Initialization**: Creates boto3 S3 client with specified AWS region
2. **EML File Listing**: Scans S3 bucket with prefix, filters for .eml files, returns sorted list
3. **Per-File Processing Loop** (for each EML file):
   - **Download**: Downloads EML file from S3 to temporary local directory
   - **Parse**: Parses EML file to extract email metadata (subject, sender, body, attachments)
   - **Save Attachments**: Saves email attachments to attachments directory with prefix-based naming
   - **Delete**: Optionally deletes processed EML file from S3
   - **Cleanup**: Removes temporary downloaded file
4. **Output Writing**: Aggregates all processed email records into JSON output file (executes after all files are processed)
5. **Product Extraction** (optional): If enabled, calls Flow 2 to process attachments and extract products (executes after output writing, uses email records to create sender mapping)

### Output Data

- **Email records JSON**: Aggregated file containing all processed email metadata
- **Attachments directory**: Extracted email attachments saved with prefix naming
- **Sender mapping file**: JSON mapping file linking attachment prefixes to sender information
- **Extraction outputs**: If extraction enabled, Flow 2 outputs (responses, logs, metadata)

## Data Interface

### Step 1 Output (`step1_init_s3`)

- `success`: Boolean indicating initialization success
- `s3_client`: Boto3 S3 client instance
- `error`: Error message if initialization failed

### Step 2 Output (`step2_list_eml`)

- `success`: Boolean indicating listing success
- `eml_files`: List of file dictionaries, each containing:
  - `key`: S3 object key
  - `filename`: Base filename extracted from key
- `error`: Error message if listing failed

### Step 3 Output (`step3_download_eml`)

Per-file result dictionary:

- `success`: Boolean indicating download success
- `error`: Error message if download failed

### Step 4 Output (`step4_parse_eml`)

Per-file result dictionary:

- `success`: Boolean indicating parsing success
- `record`: Email record dictionary containing:
  - `subject`: Email subject
  - `sender_email`: Sender email address
  - `sender_name`: Sender display name
  - `body`: Email body text
  - `attachments`: List of attachment dictionaries with path and metadata
  - `s3_key`: Original S3 object key
  - `s3_bucket`: S3 bucket name
  - `eml_path`: S3 URI path
- `error`: Error message if parsing failed

### Step 5 Output (`step5_delete_eml`)

Per-file result dictionary:

- `success`: Boolean indicating deletion success
- `skipped`: Boolean indicating if deletion was skipped (only present when skipped=True)
- `s3_key`: S3 object key that was deleted (only present when skipped=True)
- `error`: Error message if deletion failed

### Step 6 Output (`step6_extract_products`)

- `success`: Boolean indicating extraction success
- `skipped`: Boolean indicating if extraction was skipped
- `message`: Informational message about extraction status
- `log_file`: Path to extraction log file (present when extraction runs)
- `error`: Error message if extraction failed

**Step 6 Input Parameters:**

- `dir_manager`: DirectoryManager instance
- `prompt_file`: Path to prompt file for extraction
- `extraction_out_dir`: Output directory for extraction results
- `records`: List of email records from step4 (used to create sender mapping file)

### Step 7 Output (`step7_write_output`)

- `success`: Boolean indicating write success
- `output_path`: Path to written JSON output file
- `error`: Error message if write failed

### Email Records JSON Structure

- `generated_at`: ISO timestamp of generation
- `count`: Total number of email records
- `processed_count`: Number of successfully processed files
- `failed_count`: Number of failed files
- `deletion_failed_count`: Number of deletion failures
- `emails`: Array of email record dictionaries

### FlowResults Container

The main orchestration maintains a `FlowResults` container that aggregates:

- Step execution results (step1 through step7)
- Processing statistics (processed_count, failed_count, deletion_failed_count)
- Collected email records array
- Accessor properties for S3 client and EML files list

## File Structure

```
flow1/
├── flow1.py                    # Main orchestration file
├── step1_init_s3.py            # Initialize S3 client
├── step2_list_eml.py           # List EML files from S3
├── step3_download_eml.py       # Download EML file from S3
├── step4_parse_eml.py          # Parse EML file and extract data
├── step5_delete_eml.py        # Delete EML file from S3
├── step6_extract_products.py   # Trigger Flow 2 for product extraction
├── step7_write_output.py       # Write aggregated JSON output
└── README.md                   # This file
```

## Dependencies

- boto3: AWS SDK for Python (S3 operations)
- parse_eml: EML parsing module (from root `parse_eml.py`)
- DirectoryManager: Directory management utility (from `flow/utils/directory_manager.py`)
- Logger: Logging utility (from `flow/utils/logger.py`)
- Flow 2: Product extraction flow (from `flow/flow2/flow2.py`)

## Environment Variables

- `S3_BUCKET`: S3 bucket name (default: `pipe-and-ro-email`)
- `S3_PREFIX`: S3 prefix path (default: `exports/raw_emails`)
- `AWS_REGION`: AWS region (default: `ap-southeast-1`)
- `OUTPUT_DIR`: Base output directory (default: `.`)
- `TEMP_DIR`: Temporary download directory name (default: `temp_eml_downloads`)
- `DELETE_EML_AFTER_PROCESS`: Enable S3 deletion after processing (default: `true`)
- `ENABLE_EXTRACTION`: Enable product extraction via Flow 2 (default: `false`)
- `EXTRACTION_PROMPT_FILE`: Path to prompt file for Flow 2 extraction
- `EXTRACTION_OUT_DIR`: Output directory for extraction results (optional)

## Usage

The flow is executed via the main `flow1.py` script. Configuration is provided through environment variables. The script can be run directly or imported as a module.

## Output Structure

```
{OUTPUT_DIR}/
├── attachments_from_eml/
│   ├── eml0001_01_file1.pdf
│   ├── eml0001_02_file2.pdf
│   ├── eml0002_01_file3.pdf
│   └── sender_mapping.json
├── extraction_outputs/          # If extraction enabled
│   ├── logs/
│   │   └── extraction_TIMESTAMP.log
│   ├── responses/
│   │   └── ...
│   └── run-metadata.json
├── temp_eml_downloads/          # Temporary (cleaned up after processing)
└── emails.json                  # Aggregated email records
```

## Error Handling

- Step failures are tracked in result dictionaries with `success` boolean and `error` message
- Per-file processing errors are captured without stopping the entire flow
- Failed files are counted but processing continues for remaining files
- S3 deletion failures are tracked separately from processing failures
- Exit codes: 0 for success, 1 for errors
- Temporary files are cleaned up even if processing fails

## Relationship to Other Flows

- **Flow 2**: Flow 1 can optionally trigger Flow 2 to extract products from email attachments. Flow 1 prepares attachments and creates sender mapping, then calls Flow 2 as a subprocess. Flow 2 processes the attachments and writes extraction results to the extraction output directory.

Flow 1 serves as the entry point for processing emails from S3, while Flow 2 handles the downstream product extraction task.
