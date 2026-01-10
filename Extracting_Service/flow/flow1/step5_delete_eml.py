#!/usr/bin/env python3
"""Step 5: Delete EML file from S3."""
from typing import Any, Dict
from botocore.exceptions import ClientError, BotoCoreError


def execute(s3_client, bucket: str, key: str) -> Dict[str, Any]:
    """
    Delete a file from S3.
    
    Args:
        s3_client: Boto3 S3 client
        bucket: S3 bucket name
        key: S3 object key to delete
        
    Returns:
        Dict with 'success' bool and optional 'error' message
    """
    try:
        s3_client.delete_object(Bucket=bucket, Key=key)
        return {
            "success": True,
        }
    except (ClientError, BotoCoreError) as e:
        return {
            "success": False,
            "error": str(e),
        }
