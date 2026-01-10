#!/usr/bin/env python3
"""Main orchestration file for product extraction from linesheets flow."""
import argparse
import os
import sys
import time
from typing import Any, Dict, List, Optional

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

# Import directory manager
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from utils.directory_manager import DirectoryManager

# Import steps
from step1_init import execute as step1_init
from step2_collect_files import execute as step2_collect_files
from step3_process_file_with_llm import execute as step3_process_file
from step4_create_products_to_dynamo import execute as step4_create_products
from step5_write_metadata import execute as step5_write_metadata
from step6_delete_files import execute as step6_delete_files

# Defaults
DEFAULT_MODEL = "gpt-4.1-mini"
DEFAULT_MAX_OUTPUT_TOKENS = 20000


def eprint(*args, **kwargs) -> None:
    """Print to stderr."""
    print(*args, file=sys.stderr, **kwargs)


def utc_now_iso() -> str:
    """Get current UTC time as ISO string."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


class FlowResults:
    """Container for all step execution results."""
    
    def __init__(self, dir_manager: DirectoryManager):
        # Directory manager instance
        self.dir_manager: DirectoryManager = dir_manager
        
        # Step 1: Initialize
        self.step1: Optional[Dict[str, Any]] = None
        
        # Step 2: Collect files
        self.step2: Optional[Dict[str, Any]] = None
        
        # Step 3: Process files (per file, stored as list)
        self.step3: List[Dict[str, Any]] = []
        
        # Step 4: Create products via Dynamo
        self.step4: Optional[Dict[str, Any]] = None
        
        # Step 5: Write metadata
        self.step5: Optional[Dict[str, Any]] = None
        
        # Step 6: Delete files
        self.step6: Optional[Dict[str, Any]] = None
        
        # Processing statistics
        self.file_results: List[Dict[str, Any]] = []
    
    @property
    def openai_client(self):
        """Get OpenAI client from step1 result."""
        return self.step1.get("openai_client") if self.step1 else None
    
    @property
    def dynamo_client(self):
        """Get DynamoServiceClient from step1 result."""
        return self.step1.get("dynamo_client") if self.step1 else None
    
    @property
    def prompt(self):
        """Get prompt from step1 result."""
        return self.step1.get("prompt") if self.step1 else None
    
    @property
    def run_dir(self):
        """Get run directory from directory manager."""
        return self.dir_manager.get_run_dir()
    
    @property
    def responses_dir(self):
        """Get responses directory from directory manager."""
        return self.dir_manager.get_responses_dir()
    
    @property
    def files(self):
        """Get files list from step2 result."""
        return self.step2.get("files", []) if self.step2 else []
    
    def has_failures(self) -> bool:
        """Check if any step has failed."""
        if self.step1 and not self.step1.get("success"):
            return True
        if self.step2 and not self.step2.get("success"):
            return True
        if self.step4 and not self.step4.get("success"):
            return True
        if self.step5 and not self.step5.get("success"):
            return True
        if self.step6 and not self.step6.get("success"):
            return True
        return any(not r.get("success", True) for r in self.step3)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--attachment_dir", required=True, help="Directory containing attachment files to upload")
    ap.add_argument("--prompt_file", required=True, help="Path to a text file containing the prompt")
    ap.add_argument("--model", default=DEFAULT_MODEL, help=f"Model name (default: {DEFAULT_MODEL})")
    ap.add_argument("--ext", nargs="*", default=None, help="Extensions to include, e.g. .pdf .txt .md (default: all)")
    ap.add_argument("--recursive", action="store_true", help="Recurse into subdirectories")
    
    ap.add_argument("--max_files", type=int, default=50, help="Max number of files to process (default: 50)")
    default_max_bytes = int(os.getenv("MAX_BYTES", "20000000"))
    ap.add_argument("--max_bytes", type=int, default=default_max_bytes, help=f"Skip files larger than this (default: {default_max_bytes} bytes)")
    ap.add_argument("--max_output_tokens", type=int, default=DEFAULT_MAX_OUTPUT_TOKENS, help="Max output tokens")
    
    ap.add_argument("--out_dir", default="./outputs", help="Directory where outputs are written")
    ap.add_argument("--no_run_subdir", action="store_true", help="Write outputs directly into --out_dir (no run_*)")
    ap.add_argument("--response_ext", default=".txt", help="Per-file response file extension (.txt/.md/.json)")
    ap.add_argument("--upload_purpose", default="assistants", help="OpenAI file upload purpose (default: assistants)")
    
    args = ap.parse_args()
    
    # Parse DELETE_FILE_AFTER_PROCESS env var (default: False to prevent accidental deletion)
    DELETE_FILE_AFTER_PROCESS = os.getenv("DELETE_FILE_AFTER_PROCESS", "false").lower() in ("true", "1", "yes")
    
    # Initialize directory manager
    dir_manager = DirectoryManager(args.out_dir)
    if not args.no_run_subdir:
        dir_manager.setup_flow2_directories(make_run_subdir=True)
    else:
        dir_manager.setup_flow2_directories(make_run_subdir=False)
    
    # Initialize results container
    results = FlowResults(dir_manager)
    
    run_started = time.time()
    run_started_iso = utc_now_iso()
    
    # Step 1: Initialize
    eprint(f"\n=== Step 1: Initialize ===")
    results.step1 = step1_init(
        dir_manager=dir_manager,
        prompt_file=args.prompt_file,
    )
    if not results.step1["success"]:
        eprint(f"ERROR initializing: {results.step1.get('error')}")
        return 2
    eprint(f"✓ OpenAI client initialized")
    if results.dynamo_client:
        eprint(f"✓ DynamoServiceClient initialized")
    else:
        eprint(f"⚠ DynamoServiceClient not available (products will be extracted but not created)")
    eprint(f"✓ Prompt loaded from: {results.step1.get('prompt_path')}")
    eprint(f"✓ Run directory: {dir_manager.get_run_dir()}")
    eprint(f"Delete After Process: {DELETE_FILE_AFTER_PROCESS}")
    
    # Step 2: Collect files
    eprint(f"\n=== Step 2: Collect Files ===")
    eprint(f"Scanning directory: {args.attachment_dir}")
    results.step2 = step2_collect_files(
        input_dir=args.attachment_dir,
        exts=args.ext,
        recursive=bool(args.recursive),
        max_files=args.max_files,
        max_bytes=args.max_bytes,
    )
    if not results.step2["success"]:
        eprint(f"ERROR collecting files: {results.step2.get('error')}")
        return 2
    
    files = results.files
    if not files:
        eprint("No files found to process.")
        return 0
    
    eprint(f"Found {results.step2.get('total_found')} file(s), collecting {len(files)} file(s)")
    
    # Step 3: Process each file
    eprint(f"\n=== Step 3: Process Files ===")
    for i, file_info in enumerate(files, start=1):
        file_path = file_info["path"]
        file_name = file_info["name"]
        file_size_bytes = file_info["size_bytes"]
        
        eprint(f"\n[{i}/{len(files)}] Processing: {file_name} ({file_size_bytes} bytes)")
        
        step3_result = step3_process_file(
            dir_manager=dir_manager,
            openai_client=results.openai_client,
            file_path=file_path,
            file_name=file_name,
            file_size_bytes=file_size_bytes,
            prompt=results.prompt,
            model=args.model,
            max_output_tokens=args.max_output_tokens,
            response_ext=args.response_ext,
            upload_purpose=args.upload_purpose,
        )
        results.step3.append(step3_result)
        
        if step3_result["success"]:
            file_result = step3_result["file_result"]
            eprint(f"  ✓ Uploaded: {file_result.get('uploaded_file_id', 'N/A')}")
            eprint(f"  ✓ Response written: {file_result.get('response_path', 'N/A')}")
            if file_result.get("products_extracted", 0) > 0:
                eprint(f"  ✓ Products extracted: {file_result.get('products_extracted')}")
            results.file_results.append(file_result)
        else:
            file_result = step3_result.get("file_result", {})
            eprint(f"  ✗ Error: {file_result.get('error', 'Unknown error')}")
            results.file_results.append(file_result)
    
    # Aggregate statistics
    files_uploaded = sum(1 for r in results.file_results if r.get("uploaded_file_id"))
    files_ok = sum(1 for r in results.file_results if r.get("status") == "ok")
    files_skipped = sum(1 for r in results.file_results if r.get("status") == "skipped")
    files_error = sum(1 for r in results.file_results if r.get("status") == "error")
    total_products_extracted = sum(r.get("products_extracted", 0) for r in results.file_results)
    
    # Step 4: Create products via Dynamo
    eprint(f"\n=== Step 4: Create Products ===")
    results.step4 = step4_create_products(
        dynamo_client=results.dynamo_client,
        file_results=results.file_results, 
    )
    
    if not results.step4["success"]:
        eprint(f"ERROR creating products: {results.step4.get('error')}")
        return 1
    
    step4_result = results.step4.get("step_result", {})
    if step4_result.get("status") == "skipped":
        eprint(f"⚠ DynamoServiceClient not available (products will be extracted but not created)")
    else:
        eprint(f"✓ Products processed: {step4_result.get('total_products_processed', 0)}")
        eprint(f"✓ Products created: {step4_result.get('total_products_created_success', 0)} success, {step4_result.get('total_products_created_error', 0)} errors")
    
    # Update file_results with step4 results
    results.file_results = step4_result.get("file_results_updated", results.file_results)
    total_products_created_success = sum(r.get("products_created_success", 0) for r in results.file_results)
    total_products_created_error = sum(r.get("products_created_error", 0) for r in results.file_results)
    
    # Step 6: Delete processed files
    eprint(f"\n=== Step 6: Delete Files ===")
    results.step6 = step6_delete_files(
        file_results=results.file_results,
        delete_enabled=DELETE_FILE_AFTER_PROCESS,
        step4_status=step4_result.get("status", "unknown"),
    )
    
    if not results.step6["success"]:
        eprint(f"ERROR deleting files: {results.step6.get('error')}")
        # Continue execution even if deletion fails
    
    step6_result = results.step6.get("step_result", {})
    if step6_result.get("status") == "skipped":
        eprint(f"ℹ File deletion skipped: {step6_result.get('error', 'Unknown reason')}")
    elif step6_result.get("status") == "ok":
        deleted_count = step6_result.get("deleted_count", 0)
        failed_delete_count = step6_result.get("failed_delete_count", 0)
        if deleted_count > 0:
            for deleted_file in step6_result.get("deleted_files", []):
                eprint(f"  ✓ Deleted: {deleted_file.get('name', deleted_file.get('path', 'N/A'))}")
            eprint(f"✓ Deleted {deleted_count} file(s)")
        if failed_delete_count > 0:
            for failed_file in step6_result.get("failed_files", []):
                eprint(f"  ✗ Failed to delete {failed_file.get('name', failed_file.get('path', 'N/A'))}: {failed_file.get('error', 'Unknown error')}")
            eprint(f"⚠ Failed to delete {failed_delete_count} file(s)")
    
    run_finished_iso = utc_now_iso()
    run_duration = round(time.time() - run_started, 3)
    
    # Step 5: Write metadata
    eprint(f"\n=== Step 5: Write Metadata ===")
    results.step5 = step5_write_metadata(
        dir_manager=dir_manager,
        run_started_at_utc=run_started_iso,
        run_finished_at_utc=run_finished_iso,
        duration_seconds=run_duration,
        model=args.model,
        prompt_file=results.step1.get("prompt_path", args.prompt_file),
        input_dir=args.attachment_dir,
        recursive=bool(args.recursive),
        exts=args.ext,
        max_files=args.max_files,
        max_bytes=args.max_bytes,
        max_output_tokens=args.max_output_tokens,
        response_ext=args.response_ext,
        upload_purpose=args.upload_purpose,
        files_total_seen=len(files),
        files_uploaded=files_uploaded,
        files_ok=files_ok,
        files_skipped=files_skipped,
        files_error=files_error,
        total_products_extracted=total_products_extracted,
        total_products_created_success=total_products_created_success,
        total_products_created_error=total_products_created_error,
        file_results=results.file_results,
    )
    
    if not results.step5["success"]:
        eprint(f"ERROR writing metadata: {results.step5.get('error')}")
        return 1
    
    eprint(f"✓ Metadata written: {results.step5.get('metadata_path')}")
    
    # Summary
    eprint(
        f"\n=== Processing Complete ==="
        f"\nRun dir: {dir_manager.get_run_dir()}"
        f"\nResponses dir: {dir_manager.get_responses_dir()}"
        f"\nMetadata: {results.step5.get('metadata_path')}"
        f"\nFile counts: seen={len(files)} uploaded={files_uploaded} ok={files_ok} skipped={files_skipped} error={files_error}"
        f"\nProduct counts: extracted={total_products_extracted} created_success={total_products_created_success} created_error={total_products_created_error}"
    )
    
    # Exit code: 0 if no errors, else 1
    return 0 if files_error == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
