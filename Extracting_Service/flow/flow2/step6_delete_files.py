#!/usr/bin/env python3
"""Step 6: Delete processed files if enabled."""
import os
from typing import Any, Dict, List


def execute(
    file_results: List[Dict[str, Any]],
    delete_enabled: bool,
    step4_status: str,
) -> Dict[str, Any]:
    """
    Delete processed files if deletion is enabled and extraction was successful.
    
    Args:
        file_results: List of file result dictionaries from step3/step4
        delete_enabled: Whether file deletion is enabled (from DELETE_FILE_AFTER_PROCESS env var)
        step4_status: Status from step4 ("ok", "skipped", "error") - kept for compatibility but not used
        
    Returns:
        Dict with 'success' bool and deletion results or 'error' message
    """
    step_result: Dict[str, Any] = {
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
                        step_result["deleted_files"].append({
                            "name": file_name,
                            "path": file_path,
                        })
                    except Exception as e:
                        step_result["failed_delete_count"] += 1
                        step_result["failed_files"].append({
                            "name": file_name,
                            "path": file_path,
                            "error": str(e),
                        })
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
