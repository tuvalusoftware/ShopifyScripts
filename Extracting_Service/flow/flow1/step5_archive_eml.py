#!/usr/bin/env python3
"""Step 5: Archive EML file to S3 archive bucket."""
import os
import sys
from typing import Any, Dict
from botocore.exceptions import ClientError, BotoCoreError  # type: ignore

# Setup paths for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from utils.s3_utils import ensure_s3_bucket_exists


def execute(s3_client: Any, bucket: str, key: str, archive_bucket: str, aws_region: str) -> Dict[str, Any]:
    """
    Archive a file from S3 to archive bucket, then delete from source bucket.
    
    Args:
        s3_client: Boto3 S3 client
        bucket: S3 bucket name (source bucket)
        key: S3 object key to archive
        archive_bucket: S3 bucket name for archiving
        aws_region: AWS region name
        
    Returns:
        Dict with 'success' bool, optional 'archived_key', and optional 'error' message
    """
    archived_key = f"archived_eml/{key}"
    
    try:
        # Check if archive bucket exists, create if it doesn't
        if not ensure_s3_bucket_exists(s3_client, archive_bucket, aws_region):
            return {
                "success": False,
                "error": f"Failed to access or create archive bucket '{archive_bucket}'",
            }
        
        # Copy object to archive bucket
        copy_source = {"Bucket": bucket, "Key": key}
        try:
            s3_client.copy_object(
                CopySource=copy_source,
                Bucket=archive_bucket,
                Key=archived_key
            )
        except (ClientError, BotoCoreError) as e:
            return {
                "success": False,
                "error": f"Failed to copy to archive bucket: {str(e)}",
            }
        
        # Delete object from source bucket
        delete_success = True
        delete_error = None
        try:
            s3_client.delete_object(Bucket=bucket, Key=key)
        except (ClientError, BotoCoreError) as e:
            delete_success = False
            delete_error = str(e)
            # Archive succeeded but delete failed - still return success but log warning
        
        result = {
            "success": True,
            "archived_key": archived_key,
        }
        
        if not delete_success:
            result["delete_warning"] = f"Archive succeeded but delete failed: {delete_error}"
        
        return result
        
    except (ClientError, BotoCoreError) as e:
        return {
            "success": False,
            "error": str(e),
        }
