# Extracting Service

## Overview

The Extracting Service is an automated email processing and product extraction system that processes email files (EML format) from AWS S3, extracts product information from email attachments (linesheets), and optionally creates products in Shopify via DynamoServiceClient API.

The service consists of two orchestrated flows:

- **Flow 1**: Processes EML files from S3, extracts attachments, and optionally triggers product extraction
- **Flow 2**: Extracts product information from linesheet files using OpenAI's Responses API and optionally creates products in Shopify

## Architecture

The service follows a modular, step-based architecture where each flow is composed of sequential steps, each implemented as a separate module. This design enables clear separation of concerns, easy testing, and maintainability.

### Flow 1: S3 EML Processing

Flow 1 orchestrates 7 sequential steps:

1. Initialize S3 client
2. List EML files from S3 bucket
3. Download EML files (per-file loop)
4. Parse EML files and extract metadata/attachments (per-file loop)
5. Archive processed EML files to archive bucket (per-file loop)
6. Extract products from attachments via Flow 2 (optional)
7. Write aggregated JSON output

Flow 1 processes emails in batch, handling each file independently to ensure resilience. Steps 3-5 execute per file in a loop, while steps 1, 2, 6, and 7 execute once per run.

### Flow 2: Product Extraction from Linesheets

Flow 2 orchestrates 6 sequential steps:

1. Initialize OpenAI client, DynamoServiceClient (optional), and directories
2. Collect files from input directory with filtering
3. Process files with OpenAI Responses API (per-file loop)
4. Extract images from PDFs based on bounding box coordinates
5. Create products via DynamoServiceClient API (optional)
6. Delete processed files (optional)

Flow 2 can be executed independently or triggered by Flow 1 as a downstream processing step.

## Features

### Flow 1 Features

- S3 bucket scanning for EML files with prefix filtering
- Batch processing of multiple EML files
- Email parsing with attachment extraction
- Attachment saving with prefix-based naming for sender tracking
- Optional S3 file archiving to archive bucket after successful processing
- Integration with Flow 2 for product extraction from attachments
- Sender mapping file generation for product extraction
- Comprehensive JSON output with processing statistics
- Per-file error handling without stopping entire flow

### Flow 2 Features

- Batch processing of multiple files from a directory
- File filtering by extension and size
- Recursive directory scanning option
- OpenAI file upload and Responses API integration
- Automatic product extraction from model responses
- Sender information enrichment based on filename prefix mapping
- Image extraction from PDFs using bounding box coordinates
- Canary detection for image positioning (ABOVE, LEFT, NONE)
- Optional S3 sync for extracted images with presigned URLs
- Optional product creation via DynamoServiceClient API
- Optional file deletion after successful processing
- Comprehensive metadata tracking and logging
- Per-file processing results and statistics

## Data Flow

### Flow 1 Data Flow

**Input:**

- S3 bucket containing EML files
- S3 prefix path for filtering
- AWS region configuration
- Output directory path
- Optional extraction prompt file
- Configuration flags (enable extraction, enable archiving)
- Archive bucket name (if archiving enabled)

**Processing:**

1. S3 client initialization with AWS credentials
2. EML file listing from S3 bucket with prefix filter
3. Per-file processing loop:
   - Download EML file to temporary local directory
   - Parse EML to extract metadata (subject, sender, body, attachments)
   - Save attachments to attachments directory with prefix naming
   - Archive processed EML to archive bucket (optional)
   - Clean up temporary files
4. Aggregate email records and write JSON output
5. Trigger Flow 2 for product extraction (optional)

**Output:**

- Email records JSON file with aggregated metadata
- Attachments directory with extracted files
- Sender mapping JSON file for Flow 2
- Extraction outputs (if Flow 2 enabled): responses, logs, metadata, images

### Flow 2 Data Flow

**Input:**

- Directory path containing linesheet files
- Prompt file for OpenAI extraction
- Optional sender mapping file for enrichment
- Configuration parameters (model, file filters, output settings)

**Processing:**

1. Initialize OpenAI client, DynamoServiceClient (optional), load prompt
2. Collect files from input directory with extension and size filtering
3. Per-file processing loop:
   - Calculate SHA256 hash
   - Upload file to OpenAI
   - Call Responses API with prompt and file
   - Parse JSON products and shipper information from response
   - Enrich products with sender information (if mapping provided)
4. Extract images from PDFs based on product bounding box coordinates
5. Sync images to S3 and generate presigned URLs (optional)
6. Create products via DynamoServiceClient API (optional)
7. Delete processed files (optional)

**Output:**

- Run directory with timestamp
- Extracted images directory (organized by PDF filename)
- Processing results in memory (logged to console)
- Products created in Shopify (if DynamoServiceClient enabled)

## File Structure

```
Extracting_Service/
├── flow/
│   ├── flow1/                    # S3 EML Processing Flow
│   │   ├── flow1.py              # Main orchestration
│   │   ├── step1_init_s3.py      # Initialize S3 client
│   │   ├── step2_list_eml.py     # List EML files from S3
│   │   ├── step3_download_eml.py # Download EML file
│   │   ├── step4_parse_eml.py    # Parse EML and extract data
│   │   ├── step5_archive_eml.py   # Archive EML to S3
│   │   ├── step6_extract_products.py # Trigger Flow 2
│   │   ├── step7_write_output.py # Write JSON output
│   │   └── README.md             # Flow 1 documentation
│   ├── flow2/                    # Product Extraction Flow
│   │   ├── flow2.py              # Main orchestration
│   │   ├── step1_init.py         # Initialize clients
│   │   ├── step2_collect_files.py # Collect files
│   │   ├── step3_process_file_with_llm.py # Process file with OpenAI
│   │   ├── step3_util.py         # Step 3 utilities
│   │   ├── step4_create_products_to_dynamo.py # Create products
│   │   ├── step5_extract_images.py # Extract images from PDFs
│   │   ├── step5_util.py         # Step 5 utilities
│   │   ├── step6_delete_files.py  # Delete processed files
│   │   └── README.md             # Flow 2 documentation
│   └── utils/                    # Shared utilities
│       ├── directory_manager.py  # Directory management
│       ├── logger.py             # Logging utility
│       └── s3_utils.py           # S3 operations
├── domain/
│   └── DynamoServiceClient/      # DynamoDB Service API client
│       ├── dynamo_client.py      # Main client implementation
│       └── DATA_INSERT_GUIDE.md  # API usage guide
├── data/                         # Data directory (outputs)
│   ├── attachments_from_eml/    # Extracted attachments
│   ├── extraction_outputs/      # Flow 2 outputs
│   └── images/                  # Extracted images
├── logs/                         # Log files
├── parse_eml.py                 # EML parsing module
├── entrypoint.sh                # Docker entrypoint script
├── run_s3_eml_processing.sh     # Flow 1 execution script
├── docker-compose.yml           # Docker Compose configuration
├── Dockerfile                   # Docker image definition
├── requirements.txt             # Python dependencies
└── crontab                      # Cron job configuration
```

## Dependencies

### Python Packages

- `boto3`: AWS SDK for Python (S3 operations)
- `python-dotenv`: Environment variable management
- `openai`: OpenAI Python SDK (file uploads and Responses API)
- `requests`: HTTP client for API calls
- `pymupdf`: PDF processing and image extraction

### External Services

- **AWS S3**: Storage for EML files and extracted images
- **OpenAI API**: Product extraction from linesheets
- **DynamoServiceClient API**: Product creation in Shopify (optional)

## Environment Variables

### Flow 1 Configuration

- `S3_BUCKET`: S3 bucket name (default: `pipe-and-ro-email`)
- `S3_PREFIX`: S3 prefix path (default: `exports/raw_emails`)
- `AWS_REGION`: AWS region (default: `ap-southeast-1`)
- `AWS_ACCESS_KEY_ID`: AWS access key ID
- `AWS_SECRET_ACCESS_KEY`: AWS secret access key
- `OUTPUT_DIR`: Base output directory (default: `.`)
- `DELETE_EML_AFTER_PROCESS`: Enable S3 archiving (default: `true`)
- `ARCHIVE_BUCKET`: S3 bucket name for archiving EML files (required when archiving enabled)
- `ENABLE_EXTRACTION`: Enable product extraction via Flow 2 (default: `false`)
- `EXTRACTION_PROMPT_FILE`: Path to prompt file for Flow 2 extraction
- `EXTRACTION_OUT_DIR`: Output directory for extraction results (optional)

### Flow 2 Configuration

- `OPENAI_API_KEY`: Required for OpenAI API access
- `MAX_BYTES`: Maximum file size in bytes (default: `20000000`)
- `OUTPUT_DIR`: Base output directory path (default: current directory)
- `DELETE_FILE_AFTER_PROCESS`: Enable file deletion after processing (default: `false`)
- `SHOP_DOMAIN`: Shop domain for DynamoServiceClient product creation
- `DYNAMO_SERVICE_API_URL`: DynamoServiceClient API base URL
- `S3_IMAGE_BUCKET`: S3 bucket name for image sync (optional)
- `AWS_REGION`: AWS region for S3 operations (default: `ap-southeast-1`)
- `S3_PRESIGNED_URL_EXPIRATION_HOURS`: Expiration time for S3 presigned URLs in hours (default: `8760`)

## Usage

### Docker Deployment

The service is designed to run in a Docker container with cron-based scheduling:

```bash
docker-compose up -d
```

The container will:

1. Apply cron jobs from `crontab` file
2. Run Flow 1 immediately on startup
3. Continue running cron daemon for scheduled executions

### Manual Execution

#### Flow 1

Flow 1 is executed via the `run_s3_eml_processing.sh` script or directly via Python:

```bash
python flow/flow1/flow1.py
```

Configuration is provided through environment variables.

#### Flow 2

Flow 2 is executed via command-line arguments:

```bash
python flow/flow2/flow2.py \
  --attachment_dir /path/to/files \
  --prompt_file /path/to/prompt.txt \
  --model gpt-4.1-mini \
  --ext .pdf .txt \
  --sender_mapping_file /path/to/mapping.json
```

See Flow 2 README for complete argument reference.

## Relationship Between Flows

Flow 1 and Flow 2 work together in a pipeline:

1. **Flow 1** processes EML files from S3, extracts attachments, and creates a sender mapping file
2. **Flow 1** optionally triggers **Flow 2** to process extracted attachments
3. **Flow 2** uses the sender mapping file to enrich products with sender information
4. **Flow 2** extracts products from linesheets and optionally creates them in Shopify

Flow 2 can also be executed independently to process local files without Flow 1.

## Error Handling

Both flows implement comprehensive error handling:

- Step failures are tracked with success flags and error messages
- Per-file processing errors are captured without stopping the entire flow
- Failed files are counted but processing continues for remaining files
- S3 operations failures are tracked separately from processing failures
- Exit codes: 0 for success, 1 for errors, 2 for initialization failures
- Temporary files are cleaned up even if processing fails

## Output Structure

### Flow 1 Output

```
{OUTPUT_DIR}/
├── attachments_from_eml/
│   ├── eml0001_01_file1.pdf
│   ├── eml0001_02_file2.pdf
│   └── sender_mapping.json
├── extraction_outputs/          # If extraction enabled
│   ├── logs/
│   ├── responses/
│   └── run-metadata.json
└── emails.json                  # Aggregated email records
```

### Flow 2 Output

```
{OUTPUT_DIR}/
└── run_YYYYMMDD_HHMMSS/
    ├── responses/               # Currently unused
    └── images/                  # Extracted images from PDFs
        └── pdf_stem/
            └── extracted_image.png
```

## Logging

Logs are written to:

- Console output (stdout/stderr)
- Log files in `logs/` directory (Flow 1)
- Extraction log files in `extraction_outputs/logs/` (Flow 2)

Log files are timestamped for easy tracking and debugging.
