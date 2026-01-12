#!/usr/bin/env python3
"""Step 3: Process a single file - upload, call model, parse products."""
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Literal, Optional, TypedDict, cast

from openai import OpenAI

# Setup paths for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from utils.logger import get_logger
from step3_util import Step3Util

# Setup logger
logger = get_logger(__name__)


# ============================================================================
# Type definitions for raw OpenAI response data
# ============================================================================

class BoundingBoxRaw(TypedDict, total=False):
    """Type definition for bounding box in raw OpenAI response."""
    x0: Optional[float]
    y0: Optional[float]
    x1: Optional[float]
    y1: Optional[float]


# Use functional syntax for TypedDict to support fields with spaces
ShipperRaw = TypedDict(
    'ShipperRaw',
    {
        'merchant_name': Optional[str],
        'currency_code': Optional[str],
        'order_number': Optional[str],
        'delivery_data': Optional[str],
    },
    total=False
)


# ============================================================================
# Type definitions for product data (preserving fields with spaces)
# ============================================================================

# Use functional syntax for TypedDict to support fields with spaces
Product = TypedDict(
    'Product',
    {
        'product_name': Optional[str],
        'style_number': Optional[str],
        'availability': Optional[str],
        'color': Optional[str],
        'color_code': Optional[str],
        'size': Optional[str],
        'season': Optional[str],
        'description': Optional[str],
        'material': Optional[str],
        'certifications': Optional[str],
        'country_of_origin': Optional[str],
        'retail_price': Optional[str],
        'ws_price': Optional[str],
        'RPR': Optional[str],
        'quantity_ordered': Optional[str],
        'style_id': Optional[str],
        'units': Optional[str],
        'unit_price': Optional[str],
        'totalL_pieces': Optional[str],
        'family': Optional[str],
        'net_price': Optional[str],
        'list_price': Optional[str],
        'discount': Optional[str],
        'total': Optional[str],
        'associated_image_bbox': Optional[BoundingBoxRaw],
        'product_name_bbox': Optional[BoundingBoxRaw],
        'store_id': Optional[str],  # Added by enrichment
        'sender_email': Optional[str],  # Added by enrichment
        'sender_name': Optional[str],  # Added by enrichment
        'extracted_image_name': Optional[str],  # Added by step5 image extraction
        'extracted_image_page': Optional[int],  # Added by step5 image extraction
        'extracted_image_position': Optional[str],  # Added by step5 image extraction
        'extracted_image_s3_url': Optional[str],  # Added by step5 S3 sync
    },
    total=False
)


class OpenAIRawResponse(TypedDict, total=False):
    """Type definition for raw OpenAI API response.
    
    This represents the exact structure returned by OpenAI, including
    fields with spaces in their names.
    """
    SHIPPER: Optional[ShipperRaw]
    products: Optional[List[Product]]


class FileResult(TypedDict, total=True):
    """Type definition for file processing result."""
    input_path: str
    input_name: str
    input_size_bytes: int
    input_sha256: str
    uploaded_file_id: Optional[str]
    status: str  # "pending", "ok", "error", "skipped"
    started_at_utc: str
    finished_at_utc: Optional[str]
    duration_seconds: Optional[float]
    response_path: Optional[str]
    error: Optional[str]
    products_extracted: int
    products: Optional[List[Product]]
    shipper: Optional[ShipperRaw]
    products_created_success: int  # Added by step4
    products_created_error: int  # Added by step4
    product_creation_errors: Optional[List[str]]  # Added by step4


class Step3Result(TypedDict):
    """Type definition for step3 process file result."""
    success: bool
    file_result: FileResult




def execute(
    openai_client: OpenAI,
    file_path: str,
    prompt: str,
    model: str,
    max_output_tokens: int,
    upload_purpose: Literal["assistants", "batch", "fine-tune", "vision", "user_data", "evals"] = "assistants",
    sender_mapping_file: Optional[str] = None,
) -> Step3Result:
    """
    Process a single file: upload, call model, parse products.
    
    This function orchestrates the processing pipeline by coordinating:
    - Side effects: file I/O, API calls, loading external data
    - Pure logic: parsing, data transformation, enrichment
    
    Args:
        openai_client: OpenAI client instance
        file_path: Path to input file
        prompt: Prompt text for model
        model: Model name
        max_output_tokens: Maximum output tokens
        upload_purpose: OpenAI file upload purpose
        sender_mapping_file: Optional path to sender mapping JSON file
        
    Returns:
        Step3Result with 'success' bool and 'file_result' containing processing results
    """
    # Initialize Step3Util instance
    util = Step3Util(openai_client)
    
    started_at_utc = Step3Util.utc_now_iso()
    t0 = time.time()
    
    # Initialize result structure
    file_result: FileResult = {
        "input_path": file_path,
        "input_name": "",
        "input_size_bytes": 0,
        "input_sha256": "",
        "uploaded_file_id": None,
        "status": "pending",
        "started_at_utc": started_at_utc,
        "finished_at_utc": None,
        "duration_seconds": None,
        "response_path": None,
        "error": None,
        "products_extracted": 0,
        "products": None,
        "shipper": None,
        "products_created_success": 0,
        "products_created_error": 0,
        "product_creation_errors": None,
    }
    
    try:
        # ===== SIDE EFFECTS: Load external data =====
        # Load file metadata from file system
        file_metadata = Step3Util.load_file_metadata(file_path)
        file_result["input_name"] = file_metadata["name"]
        file_result["input_size_bytes"] = file_metadata["size_bytes"]
        
        # Load sender mapping from file system (if provided)
        sender_mapping: Dict[str, Dict[str, str]] = {}
        if sender_mapping_file:
            sender_mapping = Step3Util.load_sender_mapping(sender_mapping_file)
        
        # ===== SIDE EFFECTS: File operations =====
        path = Path(file_path)
        file_result["input_sha256"] = Step3Util.sha256_file(path)
        
        # ===== SIDE EFFECTS: API calls =====
        # Upload file to OpenAI
        file_id = util.upload_file(path, purpose=upload_purpose)
        file_result["uploaded_file_id"] = file_id
        
        # Call OpenAI API
        response_text = util.call_responses_with_file(
            model=model,
            prompt=prompt,
            file_id=file_id,
            filename=file_result["input_name"],
            max_output_tokens=max_output_tokens,
        )
        
        # Log raw LLM response
        logger.info(f"Raw LLM response for file '{file_result['input_name']}':\n{response_text}")
        
        # ===== PURE LOGIC: Parse and transform data =====
        # Parse shipper from API response (pure function)
        shipper_raw = Step3Util.get_shipper_from_response(response_text)
        if shipper_raw:
            file_result["shipper"] = cast(ShipperRaw, shipper_raw)
        
        # Parse products from API response (pure function)
        products_raw = Step3Util.parse_products_from_response(response_text)
        
        # Enrich products with sender info (pure function)
        enriched_products_raw = Step3Util.enrich_products_with_sender_info(
            products=products_raw,
            filename=file_result["input_name"],
            sender_mapping=sender_mapping
        )
        # Convert to Product type
        enriched_products: List[Product] = [cast(Product, p) for p in enriched_products_raw]
        
        # Update result with parsed data
        file_result["products_extracted"] = len(enriched_products)
        if enriched_products:
            file_result["products"] = enriched_products
        
        file_result["status"] = "ok"
        
    except Exception as ex:
        file_result["status"] = "error"
        file_result["error"] = str(ex)
    
    finally:
        # ===== SIDE EFFECTS: Update timing metadata =====
        file_result["finished_at_utc"] = Step3Util.utc_now_iso()
        file_result["duration_seconds"] = round(time.time() - t0, 3)
    
    return {
        "success": file_result["status"] == "ok",
        "file_result": file_result,
    }
