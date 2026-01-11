#!/usr/bin/env python3
"""Step 4: Parse EML file."""
import sys
import os
from typing import Any, Dict

# Setup paths for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
import _path_setup  # noqa: F401

from parse_eml import parse_eml_file
from utils.directory_manager import DirectoryManager


def execute(
    dir_manager: DirectoryManager,
    eml_path: str,
    prefix: str,
    s3_key: str,
    s3_bucket: str,
) -> Dict[str, Any]:
    """
    Parse EML file and extract email data.
    
    Args:
        dir_manager: DirectoryManager instance
        eml_path: Path to local EML file
        prefix: Prefix for attachment filenames
        s3_key: Original S3 key
        s3_bucket: S3 bucket name
        
    Returns:
        Dict with 'success' bool and 'record' dict or 'error' message
    """
    try:
        attachments_dir = dir_manager.get_attachments_dir()
        rec = parse_eml_file(
            eml_path=eml_path,
            attachments_dir=attachments_dir,
            prefix=prefix,
            save_atts=True,
        )
        
        # Update eml_path to show S3 location instead of local temp path
        rec["s3_key"] = s3_key
        rec["s3_bucket"] = s3_bucket
        rec["eml_path"] = f"s3://{s3_bucket}/{s3_key}"
        
        return {
            "success": True,
            "record": rec,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }
