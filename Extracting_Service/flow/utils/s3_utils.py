"""S3 utility functions for bucket management."""
from typing import Any, Optional
from botocore.exceptions import ClientError  # type: ignore

from utils.logger import get_logger

logger = get_logger(__name__)


def ensure_s3_bucket_exists(
    s3_client: Any,
    bucket_name: str,
    aws_region: str,
    logger_instance: Optional[Any] = None,
) -> bool:
    """
    Ensure S3 bucket exists, create it if it doesn't.
    
    Args:
        s3_client: Boto3 S3 client instance
        bucket_name: Name of the S3 bucket
        aws_region: AWS region name
        logger_instance: Optional logger instance. If not provided, uses module logger.
        
    Returns:
        True if bucket exists or was created successfully, False otherwise
    """
    log = logger_instance if logger_instance is not None else logger
    
    try:
        # Check if bucket exists
        s3_client.head_bucket(Bucket=bucket_name)
        log.debug(f"S3 bucket '{bucket_name}' already exists")
        return True
    except ClientError as e:
        logger.error(f"Error checking S3 bucket '{bucket_name}': {e}")
        error_code: str = ""
        response = getattr(e, "response", None)
        if response and isinstance(response, dict):
            error_info = response.get("Error", {})  # type: ignore
            if isinstance(error_info, dict):
                error_code = str(error_info.get("Code", "") or "")  # type: ignore
        
        if error_code == "404":
            # Bucket doesn't exist, create it
            try:
                log.info(f"S3 bucket '{bucket_name}' not found, creating it in region '{aws_region}'")
                
                # Create bucket configuration
                if aws_region == "us-east-1":
                    # us-east-1 doesn't need LocationConstraint
                    s3_client.create_bucket(Bucket=bucket_name)
                else:
                    s3_client.create_bucket(
                        Bucket=bucket_name,
                        CreateBucketConfiguration={"LocationConstraint": aws_region}
                    )
                
                log.info(f"Successfully created S3 bucket '{bucket_name}' in region '{aws_region}'")
                return True
            except ClientError as create_error:
                # Handle case where bucket might be created by another process
                create_error_code: str = ""
                create_response = getattr(create_error, "response", None)
                if create_response and isinstance(create_response, dict):
                    create_error_info = create_response.get("Error", {})  # type: ignore
                    if isinstance(create_error_info, dict):
                        create_error_code = str(create_error_info.get("Code", "") or "")  # type: ignore
                
                if create_error_code == "BucketAlreadyOwnedByYou":
                    # Bucket was created by another process, consider it success
                    log.info(f"S3 bucket '{bucket_name}' was created by another process")
                    return True
                else:
                    log.error(f"Failed to create S3 bucket '{bucket_name}': {create_error}")
                    return False
        elif error_code == "403":
            # Access denied - bucket might exist but we don't have permission
            log.warning(
                f"Access denied when checking S3 bucket '{bucket_name}'. "
                f"Bucket may exist but you don't have permission to access it."
            )
            return False
        else:
            # Other error
            log.error(f"Error checking S3 bucket '{bucket_name}': {error_code} - {e}")
            return False
    except Exception as ex:
        log.error(f"Unexpected error checking/creating S3 bucket '{bucket_name}': {ex}")
        return False
