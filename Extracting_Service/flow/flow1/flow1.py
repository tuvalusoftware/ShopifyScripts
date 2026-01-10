#!/usr/bin/env python3
"""Main orchestration file for S3 EML processing flow."""
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime
from dotenv import load_dotenv

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

# Import directory manager
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from utils.directory_manager import DirectoryManager

# Import steps
from step1_init_s3 import execute as step1_init_s3
from step2_list_eml import execute as step2_list_eml
from step3_download_eml import execute as step3_download_eml
from step4_parse_eml import execute as step4_parse_eml
from step5_delete_eml import execute as step5_delete_eml
from step6_extract_products import execute as step6_extract_products
from step7_write_output import execute as step7_write_output

load_dotenv()


class FlowResults:
    """Container for all step execution results."""
    
    def __init__(self, dir_manager: DirectoryManager):
        # Directory manager instance
        self.dir_manager: DirectoryManager = dir_manager
        
        # Step 1: Initialize S3
        self.step1: Optional[Dict[str, Any]] = None
        
        # Step 2: List EML files
        self.step2: Optional[Dict[str, Any]] = None
        
        # Step 3: Download EML (per file, stored as list)
        self.step3: List[Dict[str, Any]] = []
        
        # Step 4: Parse EML (per file, stored as list)
        self.step4: List[Dict[str, Any]] = []
        
        # Step 5: Delete EML (per file, stored as list)
        self.step5: List[Dict[str, Any]] = []
        
        # Step 6: Extract products
        self.step6: Optional[Dict[str, Any]] = None
        
        # Step 7: Write output
        self.step7: Optional[Dict[str, Any]] = None
        
        # Processing statistics
        self.processed_count: int = 0
        self.failed_count: int = 0
        self.deletion_failed_count: int = 0
        self.records: List[Dict[str, Any]] = []
    
    @property
    def s3_client(self):
        """Get S3 client from step1 result."""
        return self.step1.get("s3_client") if self.step1 else None
    
    @property
    def eml_files(self):
        """Get EML files list from step2 result."""
        return self.step2.get("eml_files", []) if self.step2 else []
    
    def has_failures(self) -> bool:
        """Check if any step has failed."""
        if self.step1 and not self.step1.get("success"):
            return True
        if self.step2 and not self.step2.get("success"):
            return True
        if self.step6 and not self.step6.get("success"):
            return True
        if self.step7 and not self.step7.get("success"):
            return True
        return self.failed_count > 0


def main():
    # Configuration from environment variables
    s3_bucket = os.getenv("S3_BUCKET", "pipe-and-ro-email")
    s3_prefix = os.getenv("S3_PREFIX", "exports/raw_emails")
    aws_region = os.getenv("AWS_REGION", "ap-southeast-1")
    output_dir = os.getenv("OUTPUT_DIR", ".")
    temp_dir = os.getenv("TEMP_DIR", "temp_eml_downloads")
    
    # Parse DELETE_EML_AFTER_PROCESS env var (default: True to maintain current behavior)
    DELETE_EML_AFTER_PROCESS = os.getenv("DELETE_EML_AFTER_PROCESS", "true").lower() in ("true", "1", "yes")
    
    # Configuration for product extraction
    extraction_prompt_file = os.getenv("EXTRACTION_PROMPT_FILE", "")
    extraction_out_dir = os.getenv("EXTRACTION_OUT_DIR", "")
    enable_extraction = os.getenv("ENABLE_EXTRACTION", "false").lower() in ("true", "1", "yes")
    
    # Initialize directory manager
    output_dir = os.path.abspath(output_dir)
    
    # If output_dir is /app or /app/* and not writable (running locally), use local directory
    if output_dir.startswith("/app"):
        test_dir_manager = DirectoryManager(output_dir)
        if not test_dir_manager.is_writable():
            output_dir = os.path.abspath("./data")
            print(f"WARNING: Cannot write to /app, using local directory: {output_dir}")
    
    dir_manager = DirectoryManager(output_dir)
    
    # Get directory paths from directory manager
    temp_download_dir = dir_manager.get_temp_download_dir(temp_dir)
    
    print(f"=== S3 EML Processing Started: {datetime.now().isoformat()} ===")
    print(f"S3 Bucket: {s3_bucket}")
    print(f"S3 Prefix: {s3_prefix}")
    print(f"AWS Region: {aws_region}")
    print(f"Output Directory: {dir_manager.base_output_dir}")
    print(f"Temp Directory: {temp_download_dir}")
    print(f"Delete After Process: {DELETE_EML_AFTER_PROCESS}")
    
    # Initialize results container
    results = FlowResults(dir_manager)
    
    # Step 1: Initialize S3 client
    print(f"\n=== Step 1: Initialize S3 Client ===")
    results.step1 = step1_init_s3(aws_region)
    if not results.step1["success"]:
        print(f"ERROR initializing S3 client: {results.step1.get('error')}")
        return 1
    print("✓ S3 client initialized")
    
    # Step 2: List EML files
    print(f"\n=== Step 2: List EML Files ===")
    print(f"Scanning S3://{s3_bucket}/{s3_prefix} for .eml files...")
    results.step2 = step2_list_eml(results.s3_client, s3_bucket, s3_prefix)
    if not results.step2["success"]:
        print(f"ERROR listing S3 objects: {results.step2.get('error')}")
        return 1
    
    eml_files = results.eml_files
    if not eml_files:
        print("No .eml files found in S3.")
        return 0
    
    print(f"Found {len(eml_files)} .eml file(s) to process")
    
    for i, file_info in enumerate(eml_files, start=1):
        s3_key = file_info["key"]
        filename = file_info["filename"]
        
        print(f"\n[{i}/{len(eml_files)}] Processing: {filename}")
        
        # Step 3: Download file
        print(f"  === Step 3: Download EML File ===")
        temp_download_dir = dir_manager.get_temp_download_dir(temp_dir)
        local_temp_path = os.path.join(temp_download_dir, filename)
        step3_result = step3_download_eml(results.s3_client, s3_bucket, s3_key, local_temp_path)
        results.step3.append(step3_result)
        if not step3_result["success"]:
            print(f"  ERROR: Failed to download {s3_key}: {step3_result.get('error')}")
            results.failed_count += 1
            continue
        print(f"  ✓ Downloaded: {s3_key}")
        
        # Step 4: Parse EML file
        print(f"  === Step 4: Parse EML File ===")
        prefix = f"eml{i:04d}"
        try:
            step4_result = step4_parse_eml(
                dir_manager=dir_manager,
                eml_path=local_temp_path,
                prefix=prefix,
                s3_key=s3_key,
                s3_bucket=s3_bucket,
            )
            results.step4.append(step4_result)
            
            if not step4_result["success"]:
                print(f"  ERROR processing {filename}: {step4_result.get('error')}")
                results.failed_count += 1
            else:
                rec = step4_result["record"]
                results.records.append(rec)
                print(f"  ✓ Processed: {rec.get('subject') or '(no subject)'}")
                results.processed_count += 1
                
                # Step 5: Delete from S3 after successful processing (if enabled)
                if DELETE_EML_AFTER_PROCESS:
                    print(f"  === Step 5: Delete EML File from S3 ===")
                    step5_result = step5_delete_eml(results.s3_client, s3_bucket, s3_key)
                    results.step5.append(step5_result)
                    if step5_result["success"]:
                        print(f"  ✓ Deleted from S3: {s3_key}")
                    else:
                        print(f"  WARNING: Processed but failed to delete from S3: {s3_key}")
                        results.deletion_failed_count += 1
                else:
                    print(f"  ℹ Skipped deletion (DELETE_EML_AFTER_PROCESS=false): {s3_key}")
                    results.step5.append({"success": True, "skipped": True, "s3_key": s3_key})
            
        except Exception as e:
            print(f"  ERROR processing {filename}: {e}")
            results.step4.append({"success": False, "error": str(e)})
            results.failed_count += 1
        
        finally:
            # Clean up temporary downloaded file
            try:
                if os.path.exists(local_temp_path):
                    os.remove(local_temp_path)
            except Exception as e:
                print(f"  WARNING: Failed to clean up temp file {local_temp_path}: {e}")
    
    # Step 7: Write JSON output
    print(f"\n=== Step 7: Write JSON Output ===")
    results.step7 = step7_write_output(
        dir_manager=dir_manager,
        records=results.records,
        processed_count=results.processed_count,
        failed_count=results.failed_count,
        deletion_failed_count=results.deletion_failed_count,
    )
    
    if not results.step7["success"]:
        print(f"\nERROR writing JSON output: {results.step7.get('error')}")
        return 1
    print(f"✓ Wrote {results.step7['output_path']}")
    
    # Clean up temporary directory if empty
    try:
        temp_download_dir = dir_manager.get_temp_download_dir(temp_dir)
        temp_path = Path(temp_download_dir)
        if temp_path.exists() and not any(temp_path.iterdir()):
            temp_path.rmdir()
    except Exception:
        pass  # Ignore cleanup errors
    
    print(f"\n=== EML Processing Complete ===")
    print(f"Processed: {results.processed_count}")
    print(f"Failed: {results.failed_count}")
    if DELETE_EML_AFTER_PROCESS and results.deletion_failed_count > 0:
        print(f"Deletion failures: {results.deletion_failed_count}")
    print(f"Total records: {len(results.records)}")
    
    # Step 6: Extract products (if enabled)
    if enable_extraction:
        print(f"\n=== Step 6: Extract Products ===")
        if not extraction_prompt_file:
            print(f"WARNING: ENABLE_EXTRACTION is true but EXTRACTION_PROMPT_FILE is not set. Skipping extraction.")
            results.step6 = {"success": True, "skipped": True, "message": "EXTRACTION_PROMPT_FILE not set"}
        else:
            # Use extraction_out_dir if provided, otherwise use a subdirectory of output_dir
            if extraction_out_dir:
                extraction_out_dir = dir_manager.get_extraction_out_dir(extraction_out_dir)
            else:
                extraction_out_dir = dir_manager.get_extraction_out_dir()
            
            results.step6 = step6_extract_products(
                dir_manager=dir_manager,
                prompt_file=extraction_prompt_file,
                extraction_out_dir=extraction_out_dir,
            )
            
            if not results.step6["success"]:
                print(f"ERROR: {results.step6.get('error')}")
                if results.step6.get("log_file"):
                    print(f"See detailed logs in: {results.step6['log_file']}")
            elif results.step6.get("skipped"):
                print(f"INFO: {results.step6.get('message')}")
            else:
                print(f"✓ Product extraction completed successfully")
                if results.step6.get("log_file"):
                    print(f"Log file written to: {results.step6['log_file']}")
    else:
        print(f"\nINFO: Product extraction is disabled (set ENABLE_EXTRACTION=true to enable)")
        results.step6 = {"success": True, "skipped": True, "message": "Extraction disabled"}
    
    # Return error code if either EML processing or extraction failed
    extraction_failed = results.step6 and not results.step6.get("success")
    return 0 if (results.failed_count == 0 and not extraction_failed) else 1


if __name__ == "__main__":
    exit(main())
