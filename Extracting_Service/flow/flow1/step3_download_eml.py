#!/usr/bin/env python3
"""Step 3: Download EML file from S3."""
from typing import Any, Dict
from botocore.exceptions import ClientError, BotoCoreError


def execute(s3_client, bucket: str, key: str, local_path: str) -> Dict[str, Any]:
    """
    Download a file from S3 to local path.
    
    Args:
        s3_client: Boto3 S3 client
        bucket: S3 bucket name
        key: S3 object key
        local_path: Local file path to save the downloaded file
        
    Returns:
        Dict with 'success' bool and optional 'error' message
    """
    try:
        s3_client.download_file(bucket, key, local_path)
        return {
            "success": True,
        }
    except (ClientError, BotoCoreError) as e:
        return {
            "success": False,
            "error": str(e),
        }
