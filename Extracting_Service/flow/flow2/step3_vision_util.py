#!/usr/bin/env python3
"""Step3VisionUtil: Utility functions for Vision API integration in Flow2."""
import os
import sys
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, cast

import boto3  # type: ignore
from botocore.exceptions import BotoCoreError, ClientError  # type: ignore

# Setup paths for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from utils.logger import get_logger
from utils.s3_utils import ensure_s3_bucket_exists

# Setup logger
logger = get_logger(__name__)


def detect_file_type(file_path: str) -> str:
    """
    Detect if file is PDF or other type.
    
    Args:
        file_path: Path to file
        
    Returns:
        "pdf" if file is PDF, "other" otherwise
    """
    path = Path(file_path)
    ext = path.suffix.lower()
    
    if ext == ".pdf":
        return "pdf"
    return "other"


def transform_vision_product_to_flow2_product(
    vision_product: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Transform Vision API product format to Flow2 Product TypedDict format.
    
    Maps Vision API fields to Flow2 fields:
    - sku → style_number
    - wholesale_price → ws_price (convert to string)
    - retail_price → retail_price (convert to string)
    - colors (array) → color (first color) and color_code (first color or empty)
    - sizes → size (convert to string)
    - images array → keep as-is (with path and bbox)
    - _page, _source_pdf, _order_metadata → keep as-is
    - image_bboxes → associated_image_bbox (for compatibility, first bbox if exists)
    
    Args:
        vision_product: Product dictionary from Vision API extraction
        
    Returns:
        Product dictionary in Flow2 format
    """
    flow2_product: Dict[str, Any] = {}
    
    # Map core fields
    if "sku" in vision_product and vision_product["sku"] is not None:
        flow2_product["style_number"] = str(vision_product["sku"])
    
    if "product_name" in vision_product:
        flow2_product["product_name"] = vision_product["product_name"]
    
    # Map prices (convert to string)
    if "wholesale_price" in vision_product and vision_product["wholesale_price"] is not None:
        flow2_product["ws_price"] = str(vision_product["wholesale_price"])
    
    if "retail_price" in vision_product and vision_product["retail_price"] is not None:
        flow2_product["retail_price"] = str(vision_product["retail_price"])
    
    # Map colors (array to first color and color_code)
    if "colors" in vision_product and vision_product["colors"]:
        colors: Any = vision_product["colors"]
        if isinstance(colors, list) and len(colors) > 0:  # type: ignore[arg-type]
            # Type guard: ensure we can access the first element
            first_color_val: Any = colors[0]  # type: ignore[index]
            if first_color_val is not None:
                try:
                    first_color: Optional[str] = str(first_color_val)  # type: ignore[arg-type]
                except (TypeError, ValueError):
                    first_color = None
            else:
                first_color = None
            flow2_product["color"] = first_color
            flow2_product["color_code"] = first_color  # Use first color as color_code
        elif isinstance(colors, str):
            flow2_product["color"] = colors
            flow2_product["color_code"] = colors
    
    # Map sizes (convert to string)
    if "sizes" in vision_product and vision_product["sizes"] is not None:
        flow2_product["size"] = str(vision_product["sizes"])
    
    # Map other optional fields
    if "season" in vision_product:
        flow2_product["season"] = vision_product["season"]
    
    if "description" in vision_product:
        flow2_product["description"] = vision_product["description"]
    
    if "material" in vision_product:
        flow2_product["material"] = vision_product["material"]
    
    if "certifications" in vision_product:
        flow2_product["certifications"] = vision_product["certifications"]
    
    if "origin" in vision_product:
        flow2_product["country_of_origin"] = vision_product["origin"]
    
    if "quantity" in vision_product:
        flow2_product["quantity_ordered"] = str(vision_product["quantity"]) if vision_product["quantity"] is not None else None
    
    # Map image_bboxes to associated_image_bbox (for compatibility)
    # Use first bbox if available
    image_bboxes: Any = vision_product.get("image_bboxes")
    if image_bboxes and isinstance(image_bboxes, list) and len(image_bboxes) > 0:  # type: ignore[arg-type]
        first_bbox: Any = image_bboxes[0]  # type: ignore[index]
        if isinstance(first_bbox, (list, tuple)) and len(first_bbox) >= 4:  # type: ignore[arg-type]
            # Convert percentage bbox [x%, y%, w%, h%] to absolute [x0, y0, x1, y1]
            # For compatibility, we'll store as BoundingBoxRaw format
            # But note: Vision API uses percentage, Flow2 uses absolute
            # We'll keep the percentage format for now and let step5 handle conversion
            try:
                # Type guard: convert to list and extract values safely
                bbox_list: list[Any] = [first_bbox[i] for i in range(min(4, len(first_bbox)))]  # type: ignore[index, arg-type]
                flow2_product["associated_image_bbox"] = {
                    "x0": bbox_list[0] if len(bbox_list) > 0 else None,  # type: ignore[arg-type]
                    "y0": bbox_list[1] if len(bbox_list) > 1 else None,  # type: ignore[arg-type]
                    "x1": bbox_list[2] if len(bbox_list) > 2 else None,  # type: ignore[arg-type]
                    "y1": bbox_list[3] if len(bbox_list) > 3 else None,  # type: ignore[arg-type]
                }
            except (IndexError, TypeError):
                # Skip if bbox format is invalid
                pass
    
    # Keep images array as-is (with path and bbox)
    # Vision API products already have images matched with path and bbox
    if "images" in vision_product:
        flow2_product["images"] = vision_product["images"]
    
    # Keep metadata fields
    if "_page" in vision_product:
        flow2_product["_page"] = vision_product["_page"]
    
    if "_source_pdf" in vision_product:
        flow2_product["_source_pdf"] = vision_product["_source_pdf"]
    
    if "_order_metadata" in vision_product:
        flow2_product["_order_metadata"] = vision_product["_order_metadata"]
    
    # Add pdf_type if available (from extraction result)
    if "pdf_type" in vision_product:
        flow2_product["pdf_type"] = vision_product["pdf_type"]
    
    return flow2_product


def upload_images_to_s3(
    images: List[Dict[str, Any]],
    s3_bucket: Optional[str] = None,
    aws_region: Optional[str] = None,
) -> List[str]:
    """
    Upload images to S3 and return list of presigned URLs.
    
    Args:
        images: List of image dicts with 'path' and 'bbox' fields
        s3_bucket: S3 bucket name (defaults to S3_IMAGE_BUCKET env var)
        aws_region: AWS region (defaults to AWS_REGION env var or ap-southeast-1)
        
    Returns:
        List of presigned S3 URLs for uploaded images
    """
    s3_urls: List[str] = []
    
    # Get S3 bucket from env if not provided
    if not s3_bucket:
        s3_bucket = os.getenv("S3_IMAGE_BUCKET")
    
    # If no bucket configured, return empty list
    if not s3_bucket:
        logger.debug("S3_IMAGE_BUCKET not set, skipping image upload to S3")
        return s3_urls
    
    # Get AWS region
    if not aws_region:
        aws_region = os.getenv("AWS_REGION", "ap-southeast-1")
    
    try:
        # Initialize S3 client
        s3_client = boto3.client("s3", region_name=aws_region)  # type: ignore
    except Exception as ex:
        logger.error(f"Failed to initialize S3 client: {ex}")
        return s3_urls
    
    # Ensure bucket exists
    if not ensure_s3_bucket_exists(s3_client, s3_bucket, aws_region, logger_instance=logger):
        logger.error(f"Cannot proceed with S3 upload: bucket '{s3_bucket}' does not exist and could not be created")
        return s3_urls
    
    # Upload each image
    for img in images:
        image_path = img.get("path")
        if not image_path:
            continue
        
        local_image_path = Path(image_path)
        if not local_image_path.exists():
            logger.warning(f"Image file not found for upload: {local_image_path}")
            continue
        
        try:
            # Generate UUID-based filename for S3
            # Preserve original file extension
            original_ext = local_image_path.suffix
            uuid_filename = f"{uuid.uuid4()}{original_ext}"
            
            # Use product_images/UUID.ext as S3 key
            s3_key = f"product_images/{uuid_filename}"
            
            # Upload to S3
            s3_client.upload_file(  # type: ignore
                str(local_image_path),
                s3_bucket,
                s3_key,
            )
            
            # Generate presigned URL (valid for 1 year by default)
            expiration_hours = int(os.getenv("S3_PRESIGNED_URL_EXPIRATION_HOURS", "8760"))  # Default: 1 year
            expiration = timedelta(hours=expiration_hours)
            
            s3_url = cast(str, s3_client.generate_presigned_url(  # type: ignore
                "get_object",
                Params={"Bucket": s3_bucket, "Key": s3_key},
                ExpiresIn=int(expiration.total_seconds()),
            ))
            s3_urls.append(s3_url)
            
            logger.debug(f"Uploaded image to S3: {local_image_path.name} -> {s3_key} -> {s3_url}")
            
        except (ClientError, BotoCoreError, Exception) as ex:
            logger.warning(f"Failed to upload image {image_path} to S3: {ex}")
            continue
    
    return s3_urls


def process_pdf_with_vision(
    pdf_path: str,
    out_dir: str,
    config_overrides: Optional[Dict[str, Any]] = None,
    create_run_subdir: bool = False,
    doc_type: str = "auto",
) -> Dict[str, Any]:
    """
    Wrapper around extract_products_from_pdf from pdf_extraction_service.
    
    Processes a PDF file using Vision API and returns extraction results.
    
    Args:
        pdf_path: Path to PDF file
        out_dir: Output directory for extraction results
        config_overrides: Optional config overrides for extraction
        create_run_subdir: Whether to create timestamped subdirectory
        doc_type: Document type - "auto", "linesheet", or "order_confirmation"
        
    Returns:
        Dict with extraction results including products list
    """
    # Import here to avoid circular dependencies
    from services.pdf_extraction_service import extract_products_from_pdf
    
    try:
        result = extract_products_from_pdf(
            pdf_path=pdf_path,
            out_dir=out_dir,
            config_overrides=config_overrides,
            create_run_subdir=create_run_subdir,
            doc_type=doc_type,
        )
        
        # Transform products to Flow2 format and upload images to S3
        if "products" in result and result["products"]:
            transformed_products: list[Dict[str, Any]] = []
            pdf_type = result.get("pdf_type", "linesheet")
            
            # Get S3 config for image uploads
            s3_bucket = os.getenv("S3_IMAGE_BUCKET")
            aws_region = os.getenv("AWS_REGION", "ap-southeast-1")
            
            for vision_product in result["products"]:
                # Add pdf_type to each product for reference
                vision_product_dict: Dict[str, Any] = dict(vision_product)
                vision_product_dict["pdf_type"] = pdf_type
                
                # Transform to Flow2 format
                flow2_product = transform_vision_product_to_flow2_product(vision_product_dict)
                
                # Upload images to S3 and replace images array with S3 URLs
                images_data: Any = flow2_product.get("images")
                if images_data and isinstance(images_data, list):
                    images_list_len = len(images_data)  # type: ignore[arg-type]
                    if images_list_len > 0:
                        # Cast to List[Dict[str, Any]] for type checking
                        images_list: List[Dict[str, Any]] = []
                        for img_item in images_data:  # type: ignore[union-attr]
                            if isinstance(img_item, dict):
                                images_list.append(cast(Dict[str, Any], img_item))
                        
                        if images_list:
                            # Upload images to S3
                            s3_urls = upload_images_to_s3(
                                images=images_list,
                                s3_bucket=s3_bucket,
                                aws_region=aws_region,
                            )
                            # Replace images array with S3 URLs (array of strings)
                            flow2_product["images"] = s3_urls if s3_urls else None
                        else:
                            flow2_product["images"] = None
                    else:
                        flow2_product["images"] = None
                else:
                    # No images, set to None
                    flow2_product["images"] = None
                
                transformed_products.append(flow2_product)
            
            # Cast to Any to avoid type checking issues with VisionProduct vs Dict[str, Any]
            result["products"] = cast(Any, transformed_products)
        
        # Return as Dict[str, Any] to match return type
        return cast(Dict[str, Any], result)
        
    except Exception as e:
        logger.error(f"Error processing PDF with Vision API: {e}")
        raise
