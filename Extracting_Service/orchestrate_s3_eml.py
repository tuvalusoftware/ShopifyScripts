#!/usr/bin/env python3
import os
import json
import subprocess
import sys
import traceback
from typing import Any, Dict, List, Optional
from datetime import datetime
import boto3
from botocore.exceptions import ClientError, BotoCoreError

from parse_eml import parse_eml_file, ensure_dir
from dotenv import load_dotenv

load_dotenv()

def get_s3_client(region: str = "ap-southeast-1"):
    """Create and return S3 client."""
    return boto3.client("s3", region_name=region)


def list_eml_files_in_s3(s3_client, bucket: str, prefix: str) -> List[Dict[str, str]]:
    """
    List all .eml files in S3 bucket with given prefix.
    Returns list of dicts with 'key' and 'filename' fields.
    """
    eml_files: List[Dict[str, str]] = []
    
    try:
        paginator = s3_client.get_paginator("list_objects_v2")
        pages = paginator.paginate(Bucket=bucket, Prefix=prefix)
        
        for page in pages:
            if "Contents" not in page:
                continue
                
            for obj in page["Contents"]:
                key = obj["Key"]
                # Only process .eml files
                if key.lower().endswith(".eml"):
                    filename = os.path.basename(key)
                    eml_files.append({
                        "key": key,
                        "filename": filename,
                    })
        
        # Sort by key for consistent processing order
        eml_files.sort(key=lambda x: x["key"])
        return eml_files
        
    except (ClientError, BotoCoreError) as e:
        print(f"ERROR listing S3 objects: {e}")
        return []


def download_file_from_s3(s3_client, bucket: str, key: str, local_path: str) -> bool:
    """Download a file from S3 to local path."""
    try:
        s3_client.download_file(bucket, key, local_path)
        return True
    except (ClientError, BotoCoreError) as e:
        print(f"ERROR downloading {key}: {e}")
        return False


def delete_file_from_s3(s3_client, bucket: str, key: str) -> bool:
    """Delete a file from S3."""
    try:
        s3_client.delete_object(Bucket=bucket, Key=key)
        return True
    except (ClientError, BotoCoreError) as e:
        print(f"ERROR deleting {key} from S3: {e}")
        return False


def call_extract_products_script(
    attachments_dir: str,
    prompt_file: str,
    extraction_out_dir: str,
    script_path: Optional[str] = None,
) -> bool:
    """
    Call ExtractProductsFromLinesheets.py to process attachments.
    Returns True if successful, False otherwise.
    """
    if script_path is None:
        # Get the directory where this script is located
        script_dir = os.path.dirname(os.path.abspath(__file__))
        script_path = os.path.join(script_dir, "ExtractProductsFromLinesheets.py")
    
    if not os.path.exists(script_path):
        print(f"ERROR: Extraction script not found: {script_path}")
        return False
    
    # Resolve prompt file path: if relative, resolve relative to script directory
    if not os.path.isabs(prompt_file):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        prompt_file = os.path.join(script_dir, prompt_file)
        prompt_file = os.path.normpath(prompt_file)
    
    if not os.path.exists(prompt_file):
        print(f"ERROR: Prompt file not found: {prompt_file}")
        return False
    
    if not os.path.exists(attachments_dir):
        print(f"WARNING: Attachments directory does not exist: {attachments_dir}")
        return False
    
    # Check if there are any files in the attachments directory
    try:
        files_in_dir = [f for f in os.listdir(attachments_dir) if os.path.isfile(os.path.join(attachments_dir, f))]
        if not files_in_dir:
            print(f"INFO: No files found in {attachments_dir}, skipping extraction")
            return True  # Not an error, just nothing to process
    except Exception as e:
        print(f"ERROR checking attachments directory: {e}")
        return False
    
    print(f"\n=== Starting Product Extraction ===")
    print(f"Attachments directory: {attachments_dir}")
    print(f"Prompt file: {prompt_file}")
    print(f"Output directory: {extraction_out_dir}")
    
    # Create log file path in extraction output directory
    ensure_dir(extraction_out_dir)
    log_dir = os.path.join(extraction_out_dir, "logs")
    ensure_dir(log_dir)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file_path = os.path.join(log_dir, f"extraction_{timestamp}.log")
    
    try:
        # Build command
        cmd = [
            sys.executable,
            script_path,
            "--dir", attachments_dir,
            "--prompt_file", prompt_file,
            "--out_dir", extraction_out_dir,
            "--no_run_subdir",  # Write directly to out_dir without run_* subdirectory
        ]
        
        # Run the script with captured output
        result = subprocess.run(
            cmd,
            capture_output=True,  # Capture stdout and stderr
            text=True,
        )
        
        # Write all output to log file
        with open(log_file_path, "w", encoding="utf-8") as log_file:
            log_file.write(f"=== Product Extraction Log ===\n")
            log_file.write(f"Started at: {datetime.now().isoformat()}\n")
            log_file.write(f"Command: {' '.join(cmd)}\n")
            log_file.write(f"Exit code: {result.returncode}\n")
            log_file.write(f"\n{'='*60}\n")
            log_file.write(f"STDOUT:\n")
            log_file.write(f"{'='*60}\n")
            if result.stdout:
                log_file.write(result.stdout)
            else:
                log_file.write("(no stdout output)\n")
            log_file.write(f"\n{'='*60}\n")
            log_file.write(f"STDERR:\n")
            log_file.write(f"{'='*60}\n")
            if result.stderr:
                log_file.write(result.stderr)
            else:
                log_file.write("(no stderr output)\n")
            log_file.write(f"\n{'='*60}\n")
            log_file.write(f"Finished at: {datetime.now().isoformat()}\n")
        
        print(f"Log file written to: {log_file_path}")
        
        # Print captured output for debugging
        if result.stdout:
            print("=== Extraction Script STDOUT ===")
            print(result.stdout)
        if result.stderr:
            print("=== Extraction Script STDERR ===")
            print(result.stderr)
        
        if result.returncode == 0:
            print(f"\n✓ Product extraction completed successfully")
            return True
        else:
            print(f"\nERROR: Product extraction failed with exit code {result.returncode}")
            print(f"See detailed logs in: {log_file_path}")
            return False
            
    except Exception as e:
        # Log exception to file if log file was created
        error_msg = f"ERROR calling extraction script: {e}"
        print(error_msg)
        try:
            with open(log_file_path, "a", encoding="utf-8") as log_file:
                log_file.write(f"\n{error_msg}\n")
                log_file.write(traceback.format_exc())
        except Exception:
            pass  # If we can't write to log, at least we printed to console
        return False


def main():
    # Configuration from environment variables
    s3_bucket = os.getenv("S3_BUCKET", "pipe-and-ro-email")
    s3_prefix = os.getenv("S3_PREFIX", "exports/raw_emails")
    aws_region = os.getenv("AWS_REGION", "ap-southeast-1")
    output_dir = os.getenv("OUTPUT_DIR", ".")
    temp_dir = os.getenv("TEMP_DIR", "temp_eml_downloads")
    
    # Parse DELETE_AFTER_PROCESS env var (default: True to maintain current behavior)
    delete_after_process = os.getenv("DELETE_AFTER_PROCESS", "true").lower() in ("true", "1", "yes")
    
    # Configuration for product extraction
    extraction_prompt_file = os.getenv("EXTRACTION_PROMPT_FILE", "")
    extraction_out_dir = os.getenv("EXTRACTION_OUT_DIR", "")
    enable_extraction = os.getenv("ENABLE_EXTRACTION", "false").lower() in ("true", "1", "yes")
    
    # Ensure output directories exist
    output_dir = os.path.abspath(output_dir)
    
    # If output_dir is /app or /app/* and not writable (running locally), use local directory
    if output_dir.startswith("/app"):
        try:
            # Try to create a test directory to check if /app is writable
            test_dir = os.path.join(output_dir, ".test_write_check")
            os.makedirs(test_dir, exist_ok=True)
            os.rmdir(test_dir)
        except (OSError, PermissionError):
            # Fall back to local data directory
            output_dir = os.path.abspath("./data")
            print(f"WARNING: Cannot write to /app, using local directory: {output_dir}")
    
    ensure_dir(output_dir)
    
    attachments_dir = os.path.join(output_dir, "attachments_from_eml")
    ensure_dir(attachments_dir)
    
    # Create temporary directory for downloads
    temp_download_dir = os.path.join(output_dir, temp_dir)
    ensure_dir(temp_download_dir)
    
    print(f"=== S3 EML Processing Started: {datetime.now().isoformat()} ===")
    print(f"S3 Bucket: {s3_bucket}")
    print(f"S3 Prefix: {s3_prefix}")
    print(f"AWS Region: {aws_region}")
    print(f"Output Directory: {output_dir}")
    print(f"Temp Directory: {temp_download_dir}")
    print(f"Delete After Process: {delete_after_process}")
    
    # Initialize S3 client
    try:
        s3_client = get_s3_client(aws_region)
    except Exception as e:
        print(f"ERROR initializing S3 client: {e}")
        return 1
    
    # List all .eml files in S3
    print(f"\nScanning S3://{s3_bucket}/{s3_prefix} for .eml files...")
    eml_files = list_eml_files_in_s3(s3_client, s3_bucket, s3_prefix)
    
    if not eml_files:
        print("No .eml files found in S3.")
        return 0
    
    print(f"Found {len(eml_files)} .eml file(s) to process")
    
    # Process each file
    records: List[Dict[str, Any]] = []
    processed_count = 0
    failed_count = 0
    deletion_failed_count = 0
    
    for i, file_info in enumerate(eml_files, start=1):
        s3_key = file_info["key"]
        filename = file_info["filename"]
        
        print(f"\n[{i}/{len(eml_files)}] Processing: {filename}")
        
        # Download file to temporary location
        local_temp_path = os.path.join(temp_download_dir, filename)
        
        if not download_file_from_s3(s3_client, s3_bucket, s3_key, local_temp_path):
            print(f"  ERROR: Failed to download {s3_key}")
            failed_count += 1
            continue
        
        # Process the .eml file
        prefix = f"eml{i:04d}"
        try:
            rec = parse_eml_file(
                eml_path=local_temp_path,
                attachments_dir=attachments_dir,
                prefix=prefix,
                save_atts=True,
            )
            
            # Update eml_path to show S3 location instead of local temp path
            rec["s3_key"] = s3_key
            rec["s3_bucket"] = s3_bucket
            rec["eml_path"] = f"s3://{s3_bucket}/{s3_key}"
            
            records.append(rec)
            print(f"  ✓ Processed: {rec.get('subject') or '(no subject)'}")
            
            # Delete from S3 after successful processing (if enabled)
            processed_count += 1
            if delete_after_process:
                if delete_file_from_s3(s3_client, s3_bucket, s3_key):
                    print(f"  ✓ Deleted from S3: {s3_key}")
                else:
                    print(f"  WARNING: Processed but failed to delete from S3: {s3_key}")
                    deletion_failed_count += 1  # Track deletion failures separately
            else:
                print(f"  ℹ Skipped deletion (DELETE_AFTER_PROCESS=false): {s3_key}")
            
        except Exception as e:
            print(f"  ERROR processing {filename}: {e}")
            failed_count += 1
        
        finally:
            # Clean up temporary downloaded file
            try:
                if os.path.exists(local_temp_path):
                    os.remove(local_temp_path)
            except Exception as e:
                print(f"  WARNING: Failed to clean up temp file {local_temp_path}: {e}")
    
    # Write aggregated JSON output
    output_json_path = os.path.join(output_dir, "emails.json")
    output_data = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "count": len(records),
        "processed_count": processed_count,
        "failed_count": failed_count,
        "deletion_failed_count": deletion_failed_count,
        "emails": records,
    }
    
    try:
        with open(output_json_path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        print(f"\n✓ Wrote {output_json_path}")
    except Exception as e:
        print(f"\nERROR writing JSON output: {e}")
        return 1
    
    # Clean up temporary directory if empty
    try:
        if os.path.exists(temp_download_dir) and not os.listdir(temp_download_dir):
            os.rmdir(temp_download_dir)
    except Exception:
        pass  # Ignore cleanup errors
    
    print(f"\n=== EML Processing Complete ===")
    print(f"Processed: {processed_count}")
    print(f"Failed: {failed_count}")
    if delete_after_process and deletion_failed_count > 0:
        print(f"Deletion failures: {deletion_failed_count}")
    print(f"Total records: {len(records)}")
    
    # Call product extraction script if enabled
    extraction_failed = False
    if enable_extraction:
        if not extraction_prompt_file:
            print(f"\nWARNING: ENABLE_EXTRACTION is true but EXTRACTION_PROMPT_FILE is not set. Skipping extraction.")
        else:
            # Use extraction_out_dir if provided, otherwise use a subdirectory of output_dir
            if not extraction_out_dir:
                extraction_out_dir = os.path.join(output_dir, "extraction_outputs")
            
            if not call_extract_products_script(
                attachments_dir=attachments_dir,
                prompt_file=extraction_prompt_file,
                extraction_out_dir=extraction_out_dir,
            ):
                extraction_failed = True
    else:
        print(f"\nINFO: Product extraction is disabled (set ENABLE_EXTRACTION=true to enable)")
    
    # Return error code if either EML processing or extraction failed
    return 0 if (failed_count == 0 and not extraction_failed) else 1


if __name__ == "__main__":
    exit(main())

