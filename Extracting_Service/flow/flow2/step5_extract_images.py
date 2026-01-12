#!/usr/bin/env python3
"""Step 5: Extract images from PDFs near product names."""
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, cast

import boto3  # type: ignore
from botocore.exceptions import BotoCoreError, ClientError  # type: ignore

# Setup paths for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from step3_process_file_with_llm import FileResult, Product
from step5_util import extract_images_for_products
from utils.logger import get_logger
from utils.s3_utils import ensure_s3_bucket_exists

logger = get_logger(__name__)


def utc_now_iso() -> str:
    """Get current UTC time as ISO string."""
    return datetime.now(timezone.utc).isoformat()


def sync_images_to_s3(
    images_dir: Path,
    file_results_updated: List[FileResult],
    s3_bucket: str,
    aws_region: str,
) -> tuple[List[FileResult], Dict[str, int]]:
    """
    Sync extracted images to S3 bucket and update products with S3 URLs.
    
    Args:
        images_dir: Local directory containing extracted images
        file_results_updated: List of FileResult dictionaries with enriched products
        s3_bucket: S3 bucket name
        aws_region: AWS region name
        
    Returns:
        Tuple of (updated_file_results, sync_stats) where sync_stats contains:
        - total_images_synced: Number of images successfully synced
        - failed_sync_count: Number of images that failed to sync
    """
    sync_stats = {"total_images_synced": 0, "failed_sync_count": 0}
    
    try:
        # Initialize S3 client
        s3_client = boto3.client("s3", region_name=aws_region)  # type: ignore
    except Exception as ex:
        logger.error(f"Failed to initialize S3 client: {ex}")
        return file_results_updated, sync_stats
    
    # Ensure bucket exists, create if it doesn't
    if not ensure_s3_bucket_exists(s3_client, s3_bucket, aws_region, logger_instance=logger):
        logger.error(f"Cannot proceed with S3 sync: bucket '{s3_bucket}' does not exist and could not be created")
        return file_results_updated, sync_stats
    
    # Create a copy of file_results to update
    updated_results: List[FileResult] = []
    
    for file_result in file_results_updated:
        file_result_copy: FileResult = cast(FileResult, dict(file_result))
        products = file_result_copy.get("products")
        
        if not products:
            updated_results.append(file_result_copy)
            continue
        
        # Update each product with S3 URL
        updated_products: List[Product] = []
        for product in products:
            product_copy: Product = cast(Product, dict(product))
            extracted_image_name = product_copy.get("extracted_image_name")
            
            if extracted_image_name:
                # Construct local file path
                # extracted_image_name is like "pdf_stem/filename.png"
                local_image_path = images_dir / extracted_image_name
                
                if local_image_path.exists():
                    try:
                        # S3 key: remove "images/" prefix if present, keep pdf_stem/filename.png
                        # Since images_dir is already "images", extracted_image_name is relative to it
                        s3_key = extracted_image_name
                        
                        # Upload to S3
                        s3_client.upload_file(  # type: ignore
                            str(local_image_path),
                            s3_bucket,
                            s3_key,
                        )
                        
                        # Construct S3 URL
                        s3_url = f"s3://{s3_bucket}/{s3_key}"
                        product_copy["extracted_image_s3_url"] = s3_url
                        sync_stats["total_images_synced"] += 1
                        
                        logger.debug(
                            f"Synced image to S3: {extracted_image_name} -> {s3_url}"
                        )
                        
                    except (ClientError, BotoCoreError, Exception) as ex:
                        logger.warning(
                            f"Failed to sync image {extracted_image_name} to S3: {ex}"
                        )
                        product_copy["extracted_image_s3_url"] = None
                        sync_stats["failed_sync_count"] += 1
                else:
                    logger.warning(
                        f"Image file not found for sync: {local_image_path}"
                    )
                    product_copy["extracted_image_s3_url"] = None
                    sync_stats["failed_sync_count"] += 1
            else:
                # No image extracted, set S3 URL to None
                product_copy["extracted_image_s3_url"] = None
            
            updated_products.append(product_copy)
        
        file_result_copy["products"] = updated_products
        updated_results.append(file_result_copy)
    
    return updated_results, sync_stats


def execute(
    file_results: List[FileResult],
    attachment_dir: str,
    run_dir: str,
) -> Dict[str, Any]:
    """
    Extract images from PDFs for products extracted in step3.
    
    Args:
        file_results: List of file result dictionaries from step3
        attachment_dir: Directory containing original PDF files
        run_dir: Output directory for extracted images
        
    Returns:
        Dict with 'success' bool and extraction results or 'error' message
    """
    started_at_utc = utc_now_iso()
    step_result: Dict[str, Any] = {
        "status": "pending",
        "started_at_utc": started_at_utc,
        "finished_at_utc": None,
        "duration_seconds": None,
        "total_pdfs_processed": 0,
        "total_images_extracted": 0,
        "canary_counts": {"ABOVE": 0, "LEFT": 0, "NONE": 0},
        "file_results_updated": [],  # List[FileResult]
        "s3_sync_enabled": False,
        "total_images_synced": 0,
        "failed_sync_count": 0,
        "s3_bucket": None,
        "error": None,
    }

    t0 = time.time()

    try:
        attachment_dir_path = Path(attachment_dir).expanduser().resolve()
        run_dir_path = Path(run_dir).expanduser().resolve()
        run_dir_path.mkdir(parents=True, exist_ok=True)

        # Create images subdirectory in run_dir
        images_dir = run_dir_path / "images"
        images_dir.mkdir(parents=True, exist_ok=True)

        # Process each file result
        for file_result in file_results:
            file_result_updated: FileResult = cast(FileResult, dict(file_result))

            # Skip non-PDF files
            input_name = file_result.get("input_name", "")
            if not input_name.lower().endswith(".pdf"):
                file_result_updated["products"] = file_result.get("products")
                step_result["file_results_updated"].append(file_result_updated)
                continue

            # Skip files without products
            products = file_result.get("products")
            if not products:
                file_result_updated["products"] = None
                step_result["file_results_updated"].append(file_result_updated)
                continue

            # Skip files with error status
            if file_result.get("status") != "ok":
                file_result_updated["products"] = products
                step_result["file_results_updated"].append(file_result_updated)
                continue

            # Locate PDF file
            pdf_path = attachment_dir_path / input_name
            if not pdf_path.exists():
                logger.warning(
                    f"PDF file not found for {input_name}: {pdf_path}. Skipping image extraction."
                )
                file_result_updated["products"] = products
                step_result["file_results_updated"].append(file_result_updated)
                continue

            # Extract images for products
            try:
                # Cast products to List[Dict[str, Any]] for extract_images_for_products
                products_dict: List[Dict[str, Any]] = [
                    cast(Dict[str, Any], p) for p in products
                ]
                enriched_products, canary_counts = extract_images_for_products(
                    products=products_dict,
                    pdf_path=pdf_path,
                    output_dir=images_dir,
                )

                # Update products in file_result
                enriched_products_typed: List[Product] = [
                    cast(Product, p) for p in enriched_products
                ]
                file_result_updated["products"] = enriched_products_typed

                # Update statistics
                step_result["total_pdfs_processed"] += 1
                extracted_count = sum(
                    1
                    for p in enriched_products
                    if p.get("extracted_image_name") is not None
                )
                step_result["total_images_extracted"] += extracted_count
                step_result["canary_counts"]["ABOVE"] += canary_counts.get("ABOVE", 0)
                step_result["canary_counts"]["LEFT"] += canary_counts.get("LEFT", 0)
                step_result["canary_counts"]["NONE"] += canary_counts.get("NONE", 0)

                logger.info(
                    f"Extracted {extracted_count} images from {input_name} "
                    f"(ABOVE: {canary_counts.get('ABOVE', 0)}, "
                    f"LEFT: {canary_counts.get('LEFT', 0)}, "
                    f"NONE: {canary_counts.get('NONE', 0)})"
                )

            except Exception as ex:
                logger.error(f"Error extracting images from {input_name}: {ex}")
                # Keep original products on error
                file_result_updated["products"] = products

            step_result["file_results_updated"].append(file_result_updated)

        # Sync images to S3 if bucket is configured
        s3_bucket = os.getenv("S3_IMAGE_BUCKET")
        if s3_bucket:
            aws_region = os.getenv("AWS_REGION", "ap-southeast-1")
            step_result["s3_sync_enabled"] = True
            step_result["s3_bucket"] = s3_bucket
            
            logger.info(f"Syncing images to S3 bucket: {s3_bucket}")
            try:
                updated_file_results, sync_stats = sync_images_to_s3(
                    images_dir=images_dir,
                    file_results_updated=step_result["file_results_updated"],
                    s3_bucket=s3_bucket,
                    aws_region=aws_region,
                )
                step_result["file_results_updated"] = updated_file_results
                step_result["total_images_synced"] = sync_stats["total_images_synced"]
                step_result["failed_sync_count"] = sync_stats["failed_sync_count"]
                
                logger.info(
                    f"S3 sync completed: {sync_stats['total_images_synced']} synced, "
                    f"{sync_stats['failed_sync_count']} failed"
                )
            except Exception as ex:
                logger.error(f"Error during S3 sync: {ex}")
                step_result["failed_sync_count"] = step_result.get("total_images_extracted", 0)
        else:
            logger.info("S3_IMAGE_BUCKET not set, skipping image sync to S3")

        step_result["status"] = "ok"

    except Exception as ex:
        step_result["status"] = "error"
        step_result["error"] = str(ex)
        logger.error(f"Error in step5 image extraction: {ex}")

    finally:
        step_result["finished_at_utc"] = utc_now_iso()
        step_result["duration_seconds"] = round(time.time() - t0, 3)

    return {
        "success": step_result["status"] in ("ok", "skipped"),
        "step_result": step_result,
    }
