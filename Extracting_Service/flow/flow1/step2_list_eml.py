#!/usr/bin/env python3
"""Step 2: List EML files from S3."""
import os
from typing import Any, Dict, List
from botocore.exceptions import ClientError, BotoCoreError  # type: ignore


def execute(s3_client: Any, bucket: str, prefix: str) -> Dict[str, Any]:
    """
    List all .eml files in S3 bucket with given prefix.
    
    Args:
        s3_client: Boto3 S3 client
        bucket: S3 bucket name
        prefix: S3 prefix to search
        
    Returns:
        Dict with 'success' bool and 'eml_files' list or 'error' message
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
        return {
            "success": True,
            "eml_files": eml_files,
        }
        
    except (ClientError, BotoCoreError) as e:
        return {
            "success": False,
            "error": str(e),
            "eml_files": [],
        }
