#!/usr/bin/env python3
"""Step 7: Write JSON output."""
import os
import sys
import json
from typing import Any, Dict, List
from datetime import datetime

# Import directory manager
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from utils.directory_manager import DirectoryManager


def execute(
    dir_manager: DirectoryManager,
    records: List[Dict[str, Any]],
    processed_count: int,
    failed_count: int,
    deletion_failed_count: int,
) -> Dict[str, Any]:
    """
    Write aggregated JSON output file.
    
    Args:
        dir_manager: DirectoryManager instance
        records: List of email records
        processed_count: Number of successfully processed files
        failed_count: Number of failed files
        deletion_failed_count: Number of deletion failures
        
    Returns:
        Dict with 'success' bool and 'output_path' or 'error' message
    """
    output_json_path = dir_manager.get_path("emails.json")
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
        return {
            "success": True,
            "output_path": output_json_path,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }
