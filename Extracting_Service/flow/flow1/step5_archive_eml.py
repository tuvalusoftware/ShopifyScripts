#!/usr/bin/env python3
"""Step 5: Archive EML file to S3 archive bucket."""
from typing import Any, Dict
from botocore.exceptions import ClientError, BotoCoreError  # type: ignore


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
        # Check if archive bucket exists
        try:
            s3_client.head_bucket(Bucket=archive_bucket)
        except ClientError as e:
            error_code: str = e.response.get("Error", {}).get("Code", "")  # type: ignore
            if error_code == "404":
                # Bucket doesn't exist, create it
                try:
                    if aws_region == "us-east-1":
                        # us-east-1 doesn't need LocationConstraint
                        s3_client.create_bucket(Bucket=archive_bucket)
                    else:
                        s3_client.create_bucket(
                            Bucket=archive_bucket,
                            CreateBucketConfiguration={"LocationConstraint": aws_region}
                        )
                except ClientError as create_error:
                    # Handle case where bucket might be created by another process
                    create_error_code: str = create_error.response.get("Error", {}).get("Code", "")  # type: ignore
                    if create_error_code == "BucketAlreadyOwnedByYou":
                        pass  # Bucket was created by another process, continue
                    else:
                        return {
                            "success": False,
                            "error": f"Failed to create archive bucket: {str(create_error)}",
                        }
            else:
                # Other error (access denied, etc.)
                return {
                    "success": False,
                    "error": f"Failed to access archive bucket: {str(e)}",
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
