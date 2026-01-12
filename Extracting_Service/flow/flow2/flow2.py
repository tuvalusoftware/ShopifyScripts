#!/usr/bin/env python3
"""Main orchestration file for product extraction from linesheets flow."""
import argparse
import os
import sys
from typing import Any, Dict, List, Optional, cast

# Setup paths for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
import _path_setup  # type: ignore  # noqa: F401

from utils.directory_manager import DirectoryManager
from utils.logger import get_logger

# Import steps
from step1_init import execute as step1_init
from step2_collect_files import execute as step2_collect_files
from step3_process_file_with_llm import execute as step3_process_file
from step3_process_file_with_llm import FileResult, Step3Result
from step4_create_products_to_dynamo import execute as step4_create_products
from step5_extract_images import execute as step5_extract_images
from step6_delete_files import execute as step6_delete_files
from step6_delete_files import Step6Result

# Defaults
DEFAULT_MODEL = "gpt-4.1-mini"
DEFAULT_MAX_OUTPUT_TOKENS = 20000

# Setup logger
logger = get_logger(__name__)


class State:
    """Container for all step execution results."""
    
    def __init__(self, dir_manager: DirectoryManager):
        # Directory manager instance
        self.dir_manager: DirectoryManager = dir_manager
        
        # Step 1: Initialize
        self.step1: Optional[Dict[str, Any]] = None
        
        # Step 2: Collect files
        self.step2: Optional[Dict[str, Any]] = None
        
        # Step 3: Process files (per file, stored as list)
        self.step3: List[Step3Result] = []
        
        # Step 4: Create products via Dynamo
        self.step4: Optional[Dict[str, Any]] = None
        
        # Step 5: Extract images from PDFs
        self.step5: Optional[Dict[str, Any]] = None
        
        # Step 6: Delete files
        self.step6: Optional[Step6Result] = None
        
        # Processing statistics
        self.file_results: List[FileResult] = []
    
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
    def files(self) -> List[Dict[str, Any]]:
        """Get files list from step2 result."""
        if not self.step2:
            return []
        files = self.step2.get("files", [])
        return cast(List[Dict[str, Any]], files)
    
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
    ap.add_argument("--sender_mapping_file", default=None, help="Path to sender mapping JSON file (maps prefix to sender_email and sender_name)")
    
    args = ap.parse_args()
    
    # Parse DELETE_FILE_AFTER_PROCESS env var (default: False to prevent accidental deletion)
    DELETE_FILE_AFTER_PROCESS = os.getenv("DELETE_FILE_AFTER_PROCESS", "false").lower() in ("true", "1", "yes")
    
    # Initialize directory manager (reads OUTPUT_DIR from environment variable)
    dir_manager = DirectoryManager.get_instance()
    if not args.no_run_subdir:
        dir_manager.setup_flow2_directories(make_run_subdir=True)
    else:
        dir_manager.setup_flow2_directories(make_run_subdir=False)
    
    # Initialize state container
    state = State(dir_manager)
    
    # Step 1: Initialize
    logger.info(f"\n=== Step 1: Initialize ===")
    state.step1 = step1_init(
        dir_manager=dir_manager,
        prompt_file=args.prompt_file,
    )
    if not state.step1["success"]:
        logger.error(f"ERROR initializing: {state.step1.get('error')}")
        return 2
    logger.info(f"✓ OpenAI client initialized")
    if state.dynamo_client:
        logger.info(f"✓ DynamoServiceClient initialized")
    else:
        logger.warning(f"⚠ DynamoServiceClient not available (products will be extracted but not created)")
    logger.info(f"✓ Prompt loaded from: {state.step1.get('prompt_path')}")
    logger.info(f"✓ Run directory: {dir_manager.get_run_dir()}")
    logger.info(f"Delete After Process: {DELETE_FILE_AFTER_PROCESS}")
    
    # Step 2: Collect files
    logger.info(f"\n=== Step 2: Collect Files ===")
    logger.info(f"Scanning directory: {args.attachment_dir}")
    state.step2 = step2_collect_files(
        input_dir=args.attachment_dir,
        exts=args.ext,
        recursive=bool(args.recursive),
        max_files=args.max_files,
        max_bytes=args.max_bytes,
    )
    if not state.step2["success"]:
        logger.error(f"ERROR collecting files: {state.step2.get('error')}")
        return 2
    
    files = state.files
    if not files:
        logger.info("No files found to process.")
        return 0
    
    # Ensure we have required clients and prompt
    if not state.openai_client:
        logger.error("ERROR: OpenAI client not initialized")
        return 2
    if not state.prompt:
        logger.error("ERROR: Prompt not loaded")
        return 2
    
    logger.info(f"Found {state.step2.get('total_found')} file(s), collecting {len(files)} file(s)")
    
    # Step 3: Process each file
    logger.info(f"\n=== Step 3: Process Files ===")
    for i, file_info in enumerate(files, start=1):
        file_path = str(file_info["path"])
        file_name = str(file_info["name"])
        file_size_bytes = int(file_info["size_bytes"])
        
        logger.info(f"\n[{i}/{len(files)}] Processing: {file_name} ({file_size_bytes} bytes)")
        
        step3_result = step3_process_file(
            openai_client=state.openai_client,
            file_path=file_path,
            prompt=state.prompt,
            model=args.model,
            max_output_tokens=args.max_output_tokens,
            upload_purpose=args.upload_purpose,
            sender_mapping_file=args.sender_mapping_file,
        )
        state.step3.append(step3_result)
        
        if step3_result["success"]:
            file_result = step3_result["file_result"]
            logger.info(f"  ✓ Uploaded: {file_result.get('uploaded_file_id', 'N/A')}")
            if file_result.get("products_extracted", 0) > 0:
                logger.info(f"  ✓ Products extracted: {file_result.get('products_extracted')}")
            state.file_results.append(file_result)
        else:
            file_result = step3_result.get("file_result", {})
            logger.error(f"  ✗ Error: {file_result.get('error', 'Unknown error')}")
            state.file_results.append(file_result)
    
    # Aggregate statistics
    files_uploaded = sum(1 for r in state.file_results if r.get("uploaded_file_id"))
    files_ok = sum(1 for r in state.file_results if r.get("status") == "ok")
    files_skipped = sum(1 for r in state.file_results if r.get("status") == "skipped")
    files_error = sum(1 for r in state.file_results if r.get("status") == "error")
    total_products_extracted = sum(r.get("products_extracted", 0) for r in state.file_results)
    
    # Step 5: Extract images from PDFs
    logger.info(f"\n=== Step 5: Extract Images ===")
    state.step5 = step5_extract_images(
        file_results=state.file_results,
        attachment_dir=args.attachment_dir,
        run_dir=state.run_dir,
    )
    
    step5_result: Dict[str, Any] = cast(Dict[str, Any], state.step5.get("step_result", {})) if state.step5 else {}
    if state.step5:
        if not state.step5.get("success"):
            logger.error(f"ERROR extracting images: {state.step5.get('error')}")
            # Continue execution even if image extraction fails
        else:
            if step5_result.get("status") == "ok":
                logger.info(f"✓ PDFs processed: {step5_result.get('total_pdfs_processed', 0)}")
                logger.info(f"✓ Images extracted: {step5_result.get('total_images_extracted', 0)}")
                canary_counts = cast(Dict[str, int], step5_result.get("canary_counts", {}))
                logger.info(
                    f"  Position counts: ABOVE={canary_counts.get('ABOVE', 0)}, "
                    f"LEFT={canary_counts.get('LEFT', 0)}, NONE={canary_counts.get('NONE', 0)}"
                )
            elif step5_result.get("status") == "skipped":
                logger.info(f"ℹ Image extraction skipped: {step5_result.get('error', 'Unknown reason')}")
    
    # Update file_results with step5 results
    file_results_updated = step5_result.get("file_results_updated", state.file_results)
    state.file_results = cast(List[FileResult], file_results_updated)
    
    # Step 4: Create products via Dynamo
    logger.info(f"\n=== Step 4: Create Products ===")
    state.step4 = step4_create_products(
        dynamo_client=state.dynamo_client,
        file_results=state.file_results, 
    )
    
    if not state.step4["success"]:
        logger.error(f"ERROR creating products: {state.step4.get('error')}")
        return 1
    
    step4_result = state.step4.get("step_result", {})
    if step4_result.get("status") == "skipped":
        logger.warning(f"⚠ DynamoServiceClient not available (products will be extracted but not created)")
    else:
        logger.info(f"✓ Products processed: {step4_result.get('total_products_processed', 0)}")
        logger.info(f"✓ Products created: {step4_result.get('total_products_created_success', 0)} success, {step4_result.get('total_products_created_error', 0)} errors")
    
    # Update file_results with step4 results
    file_results_updated_step4 = step4_result.get("file_results_updated", state.file_results)
    state.file_results = cast(List[FileResult], file_results_updated_step4)
    total_products_created_success = sum(r.get("products_created_success", 0) for r in state.file_results)
    total_products_created_error = sum(r.get("products_created_error", 0) for r in state.file_results)
    
    # Step 6: Delete processed files
    logger.info(f"\n=== Step 6: Delete Files ===")
    state.step6 = step6_delete_files(
        file_results=state.file_results,
        delete_enabled=DELETE_FILE_AFTER_PROCESS,
    )
    
    if not state.step6 or not state.step6["success"]:
        error_msg = state.step6.get("error") if state.step6 else "Unknown error"
        logger.error(f"ERROR deleting files: {error_msg}")
        # Continue execution even if deletion fails
    
    if state.step6:
        step6_result = state.step6.get("step_result", {})
        if step6_result.get("status") == "skipped":
            logger.info(f"ℹ File deletion skipped: {step6_result.get('error', 'Unknown reason')}")
        elif step6_result.get("status") == "ok":
            deleted_count = step6_result.get("deleted_count", 0)
            failed_delete_count = step6_result.get("failed_delete_count", 0)
            if deleted_count > 0:
                for deleted_file in step6_result.get("deleted_files", []):
                    logger.info(f"  ✓ Deleted: {deleted_file.get('name', deleted_file.get('path', 'N/A'))}")
                logger.info(f"✓ Deleted {deleted_count} file(s)")
            if failed_delete_count > 0:
                for failed_file in step6_result.get("failed_files", []):
                    logger.error(f"  ✗ Failed to delete {failed_file.get('name', failed_file.get('path', 'N/A'))}: {failed_file.get('error', 'Unknown error')}")
                logger.warning(f"⚠ Failed to delete {failed_delete_count} file(s)")
    
    # Summary
    logger.info(
        f"\n=== Processing Complete ==="
        f"\nRun dir: {dir_manager.get_run_dir()}"
        f"\nResponses dir: {dir_manager.get_responses_dir()}"
        f"\nFile counts: seen={len(files)} uploaded={files_uploaded} ok={files_ok} skipped={files_skipped} error={files_error}"
        f"\nProduct counts: extracted={total_products_extracted} created_success={total_products_created_success} created_error={total_products_created_error}"
    )
    
    # Exit code: 0 if no errors, else 1
    return 0 if files_error == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
