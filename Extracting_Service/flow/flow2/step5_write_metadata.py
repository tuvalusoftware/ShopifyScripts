#!/usr/bin/env python3
"""Step 5: Write run metadata JSON file."""
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Setup paths for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
import _path_setup  # noqa: F401

from utils.directory_manager import DirectoryManager


def write_json(path: Path, obj) -> None:
    """Write JSON object to file."""
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def execute(
    dir_manager: DirectoryManager,
    run_started_at_utc: str,
    run_finished_at_utc: str,
    duration_seconds: float,
    model: str,
    prompt_file: str,
    input_dir: str,
    recursive: bool,
    exts: Optional[List[str]],
    max_files: int,
    max_bytes: int,
    max_output_tokens: int,
    response_ext: str,
    upload_purpose: str,
    files_total_seen: int,
    files_uploaded: int,
    files_ok: int,
    files_skipped: int,
    files_error: int,
    total_products_extracted: int,
    total_products_created_success: int,
    total_products_created_error: int,
    file_results: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Write run metadata JSON file.
    
    Args:
        dir_manager: DirectoryManager instance
        run_started_at_utc: Run start time (ISO format)
        run_finished_at_utc: Run finish time (ISO format)
        duration_seconds: Run duration in seconds
        model: Model name used
        prompt_file: Path to prompt file
        input_dir: Input directory path
        recursive: Whether recursive search was used
        exts: List of file extensions filtered
        max_files: Maximum files limit
        max_bytes: Maximum file size limit
        max_output_tokens: Maximum output tokens
        response_ext: Response file extension
        upload_purpose: OpenAI upload purpose
        files_total_seen: Total files seen
        files_uploaded: Total files uploaded
        files_ok: Total files processed successfully
        files_skipped: Total files skipped
        files_error: Total files with errors
        total_products_extracted: Total products extracted
        total_products_created_success: Total products created successfully
        total_products_created_error: Total products creation errors
        file_results: List of file result dictionaries
        
    Returns:
        Dict with 'success' bool and 'metadata_path' or 'error' message
    """
    try:
        run_dir = dir_manager.get_run_dir()
        metadata = {
            "run_started_at_utc": run_started_at_utc,
            "run_finished_at_utc": run_finished_at_utc,
            "duration_seconds": duration_seconds,
            "model": model,
            "prompt_file": prompt_file,
            "input_dir": input_dir,
            "recursive": recursive,
            "exts": exts,
            "max_files": max_files,
            "max_bytes": max_bytes,
            "max_output_tokens": max_output_tokens,
            "out_dir": dir_manager.base_output_dir,
            "run_dir": run_dir,
            "response_ext": response_ext if response_ext.startswith(".") else "." + response_ext,
            "upload_purpose": upload_purpose,
            "files_total_seen": files_total_seen,
            "files_uploaded": files_uploaded,
            "files_ok": files_ok,
            "files_skipped": files_skipped,
            "files_error": files_error,
            "total_products_extracted": total_products_extracted,
            "total_products_created_success": total_products_created_success,
            "total_products_created_error": total_products_created_error,
            "file_results": file_results,
        }
        
        meta_path = Path(run_dir) / "run-metadata.json"
        write_json(meta_path, metadata)
        
        return {
            "success": True,
            "metadata_path": str(meta_path),
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }
