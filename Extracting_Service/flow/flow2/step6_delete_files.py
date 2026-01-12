#!/usr/bin/env python3
"""Step 6: Delete processed files if enabled."""
import os
from typing import List, Literal, Optional, TypedDict

from step3_process_file_with_llm import FileResult


class DeletedFileInfo(TypedDict):
    """Type definition for deleted file information."""
    name: str
    path: str


class FailedFileInfo(TypedDict):
    """Type definition for failed file deletion information."""
    name: str
    path: str
    error: str


class Step6StepResult(TypedDict):
    """Type definition for step6 step result."""
    status: Literal["pending", "ok", "skipped", "error"]
    deleted_count: int
    failed_delete_count: int
    skipped_count: int
    deleted_files: List[DeletedFileInfo]
    failed_files: List[FailedFileInfo]
    error: Optional[str]


class Step6Result(TypedDict):
    """Type definition for step6 execute result."""
    success: bool
    step_result: Step6StepResult


def execute(
    file_results: List[FileResult],
    delete_enabled: bool,
) -> Step6Result:
    """
    Delete processed files if deletion is enabled and extraction was successful.
    
    Args:
        file_results: List of file result dictionaries from step3/step4
        delete_enabled: Whether file deletion is enabled (from DELETE_FILE_AFTER_PROCESS env var)
        step4_status: Status from step4 ("ok", "skipped", "error") - kept for compatibility but not used
        
    Returns:
        Step6Result with 'success' bool and deletion results or 'error' message
    """
    step_result: Step6StepResult = {
        "status": "pending",
        "deleted_count": 0,
        "failed_delete_count": 0,
        "skipped_count": 0,
        "deleted_files": [],
        "failed_files": [],
        "error": None,
    }
    
    try:
        # Check if deletion should be performed
        if not delete_enabled:
            step_result["status"] = "skipped"
            step_result["error"] = "File deletion disabled (DELETE_FILE_AFTER_PROCESS=false)"
            return {
                "success": True,
                "step_result": step_result,
            }
        
        # Delete files that were successfully extracted (step3 status = "ok")
        for file_result in file_results:
            # Delete files that were successfully extracted, regardless of step4 status
            if file_result.get("status") == "ok":
                file_path = file_result.get("input_path")
                file_name = file_result.get("input_name", file_path)
                
                if file_path and os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                        step_result["deleted_count"] += 1
                        deleted_file_info: DeletedFileInfo = {
                            "name": file_name,
                            "path": file_path,
                        }
                        step_result["deleted_files"].append(deleted_file_info)
                    except Exception as e:
                        step_result["failed_delete_count"] += 1
                        failed_file_info: FailedFileInfo = {
                            "name": file_name,
                            "path": file_path,
                            "error": str(e),
                        }
                        step_result["failed_files"].append(failed_file_info)
                else:
                    step_result["skipped_count"] += 1
        
        step_result["status"] = "ok"
        
    except Exception as ex:
        step_result["status"] = "error"
        step_result["error"] = str(ex)
    
    return {
        "success": step_result["status"] in ("ok", "skipped"),
        "step_result": step_result,
    }
