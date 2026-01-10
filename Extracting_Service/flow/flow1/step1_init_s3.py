#!/usr/bin/env python3
"""Step 1: Initialize S3 client."""
import boto3
from typing import Any, Dict


def execute(region: str = "ap-southeast-1") -> Dict[str, Any]:
    """
    Create and return S3 client.
    
    Args:
        region: AWS region name
        
    Returns:
        Dict with 'success' bool and 's3_client' or 'error' message
    """
    try:
        s3_client = boto3.client("s3", region_name=region)
        return {
            "success": True,
            "s3_client": s3_client,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }
