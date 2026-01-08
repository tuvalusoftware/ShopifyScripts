# parse_eml.py - Email Parser

A Python script that parses `.eml` (email) files and extracts email metadata, body content, and attachments into a structured JSON format.

## Overview

The script processes one or more `.eml` files and extracts:

- Sender information (raw From header and email address)
- Subject line
- Date header
- Email body (prefers plain text, falls back to HTML converted to text)
- Attachments (optionally saved to disk)

## Requirements

- Python 3.x
- Standard library only (no external dependencies required)

## Usage

### Basic Usage

Parse a single `.eml` file:

```bash
python3 parse_eml.py --input email.eml
```

Parse all `.eml` files in a directory:

```bash
python3 parse_eml.py --input /path/to/emails/
```

### Command-Line Arguments

- `--input` (required): Path to a single `.eml` file or a directory containing `.eml` files
- `--out-json` (optional): Output JSON file path (default: `emails.json`)
- `--attachments-dir` (optional): Directory to save attachments (default: `attachments_from_eml`)
- `--no-attachments` (optional): Skip saving attachments to disk (only extract metadata)

### Examples

Parse a single email and save attachments:

```bash
python3 parse_eml.py --input message.eml --out-json output.json --attachments-dir my_attachments
```

Parse all emails in a directory without saving attachments:

```bash
python3 parse_eml.py --input ./emails/ --no-attachments --out-json emails_data.json
```

Parse emails and use custom output paths:

```bash
python3 parse_eml.py --input ./inbox/ --out-json parsed_emails.json --attachments-dir ./extracted_files/
```

## Output Format

The script generates a JSON file with the following structure:

```json
{
  "count": 2,
  "emails": [
    {
      "eml_path": "/path/to/email.eml",
      "from_raw": "Sender Name <sender@example.com>",
      "sender_email": "sender@example.com",
      "subject": "Email Subject",
      "date": "Mon, 1 Jan 2024 12:00:00 +0000",
      "body_kind": "text/plain",
      "body_text": "Email body content...",
      "attachments": [
        {
          "filename": "document.pdf",
          "path": "/path/to/attachments_from_eml/eml0001_01_document.pdf",
          "content_type": "application/pdf",
          "size": 12345
        }
      ]
    }
  ]
}
```

### Output Fields

- `count`: Total number of emails processed
- `emails`: Array of email objects, each containing:
  - `eml_path`: Original path to the `.eml` file
  - `from_raw`: Full From header (decoded)
  - `sender_email`: Extracted email address from From header
  - `subject`: Email subject (decoded)
  - `date`: Date header as string
  - `body_kind`: Type of body extracted (`"text/plain"`, `"text/html"`, or empty string)
  - `body_text`: Email body content (HTML emails are converted to plain text)
  - `attachments`: Array of attachment metadata (empty if `--no-attachments` is used)

## Attachment Handling

When attachments are saved (default behavior):

- Attachments are saved to the directory specified by `--attachments-dir`
- Filenames are sanitized and prefixed with `eml####_##_` where `####` is the email index and `##` is the attachment index
- Each attachment entry in JSON includes filename, full path, content type, and size in bytes

## Notes

- The script processes emails in sorted order (alphabetically by filename)
- HTML emails are automatically converted to plain text
- MIME-encoded headers (subject, from, etc.) are automatically decoded
- Invalid characters in attachment filenames are replaced with underscores
- The script handles encoding errors gracefully by falling back to UTF-8
