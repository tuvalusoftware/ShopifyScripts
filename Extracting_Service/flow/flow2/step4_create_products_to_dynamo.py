#!/usr/bin/env python3
"""Step 4: Create products via DynamoServiceClient API."""
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, cast

# Setup paths for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from domain.DynamoServiceClient.dynamo_client import DynamoServiceClient, SupplierDTO
from step3_process_file_with_llm import FileResult, Product


def utc_now_iso() -> str:
    """Get current UTC time as ISO string."""
    return datetime.now(timezone.utc).isoformat()


def build_supplier_dto(file_result: FileResult) -> Optional[SupplierDTO]:
    """
    Build SupplierDTO from FileResult.
    
    Extracts supplier information from:
    - FileResult.shipper (ShipperRaw): merchant_name, currency_code, delivery_data
    - FileResult.products[0]: sender_email, sender_name (from first product)
    
    Args:
        file_result: FileResult from step3 containing shipper and products
        
    Returns:
        SupplierDTO if data is available, None otherwise
    """
    supplier: SupplierDTO = {}
    
    # Extract from shipper (ShipperRaw)
    shipper = file_result.get("shipper")
    if shipper:
        # Cast to Dict for safe access since TypedDict fields are optional
        shipper_dict = cast(Dict[str, Any], shipper)
        merchant_name = shipper_dict.get("merchant_name")
        currency_code = shipper_dict.get("currency_code")
        delivery_data = shipper_dict.get("delivery_data")
        
        if merchant_name:
            supplier["merchant"] = merchant_name
        if currency_code:
            supplier["currency_code"] = currency_code
        if delivery_data:
            supplier["delivery_data"] = delivery_data
    
    # Extract sender info from first product (all products in same file share same sender)
    products = file_result.get("products")
    if products and len(products) > 0:
        first_product = products[0]
        # Cast to Dict for safe access since TypedDict fields are optional
        product_dict = cast(Dict[str, Any], first_product)
        sender_email = product_dict.get("sender_email")
        sender_name = product_dict.get("sender_name")
        
        if sender_email:
            supplier["sender_email"] = sender_email
        if sender_name:
            supplier["sender_name"] = sender_name
    
    # Return None if supplier dict is empty, otherwise return supplier
    return supplier if supplier else None


def build_product_request_dto(product: Product) -> Dict[str, Any]:
    """
    Convert Product to ProductRequestDTO by removing supplier-specific fields.
    
    Removes sender_email and sender_name from product properties as these
    are handled separately in SupplierDTO.
    
    Args:
        product: Product dictionary from step3
        
    Returns:
        Dictionary suitable for ProductRequestDTO (without sender_email, sender_name)
    """
    # Fields to exclude from product properties (they go in SupplierDTO instead)
    excluded_fields = {"sender_email", "sender_name", "store_id"}
    
    # Build properties dict excluding supplier fields
    properties = {
        k: v for k, v in product.items()
        if v is not None and k not in excluded_fields
    }
    
    return properties


def create_products_from_list(
    dynamo_client: Optional[DynamoServiceClient],
    products: List[Product],
    file_result: FileResult,
) -> Tuple[int, int, List[str]]:
    """
    Create products via DynamoServiceClient API in batch.
    
    Args:
        dynamo_client: DynamoServiceClient instance (optional)
        products: List of Product dictionaries from step3
        file_result: FileResult containing shipper info and context
        
    Returns:
        Tuple of (success_count, error_count, error_messages)
    """
    success_count = 0
    error_count = 0
    error_messages: List[str] = []
    
    if not dynamo_client:
        error_count = len(products)
        error_messages = ["DynamoServiceClient not available"] * len(products)
        return success_count, error_count, error_messages
    
    if not products:
        return success_count, error_count, error_messages
    
    # Read shop_domain from environment variable
    shop_domain: Optional[str] = os.getenv("SHOP_DOMAIN")
    
    # Build supplier DTO from file_result
    supplier = build_supplier_dto(file_result)
    
    # Convert all products to ProductRequestDTO format (removing supplier fields)
    product_dtos: List[Dict[str, Any]] = []
    invalid_products: List[str] = []
    
    for idx, product in enumerate(products):
        try:
            properties = build_product_request_dto(product)
            
            if not properties:
                invalid_products.append(f"Product at index {idx} has no properties")
                continue
            
            product_dtos.append(properties)
        except Exception as ex:
            product_name = product.get('product_name', f'unknown_{idx}')
            invalid_products.append(f"Failed to prepare product '{product_name}': {str(ex)}")
    
    # If no valid products, return error
    if not product_dtos:
        error_count = len(products)
        error_messages = invalid_products if invalid_products else ["No valid products to create"]
        return success_count, error_count, error_messages
    
    # Call batch API to create all products at once
    try:
        result = dynamo_client.create_products_batch(
            products=product_dtos,
            shop_domain=shop_domain,
            supplier=supplier,
        )
        
        # Extract success/error counts from API response
        if result.get("success"):
            imported = result.get("imported", 0)
            failed = result.get("failed", 0)
            
            success_count = imported
            error_count = failed + len(invalid_products)
            
            # Add API errors if any
            api_errors = result.get("errors", [])
            if api_errors:
                error_messages.extend([str(err) for err in api_errors])
            
            # Add invalid product errors
            if invalid_products:
                error_messages.extend(invalid_products)
        else:
            # API call failed entirely
            error_count = len(product_dtos) + len(invalid_products)
            error_msg = result.get("message", "Unknown error from API")
            error_messages.append(f"Batch API call failed: {error_msg}")
            if invalid_products:
                error_messages.extend(invalid_products)
                
    except Exception as ex:
        # Batch API call raised an exception
        error_count = len(product_dtos) + len(invalid_products)
        error_msg = f"Failed to create products batch: {str(ex)}"
        error_messages.append(error_msg)
        if invalid_products:
            error_messages.extend(invalid_products)
    
    return success_count, error_count, error_messages


def execute(
    dynamo_client: Optional[DynamoServiceClient],
    file_results: List[FileResult],
) -> Dict[str, Any]:
    """
    Create products via DynamoServiceClient API for all files that have extracted products.
    
    Args:
        dynamo_client: DynamoServiceClient instance (optional)
        file_results: List of file result dictionaries from step3
        
    Returns:
        Dict with 'success' bool and creation results or 'error' message
    """
    started_at_utc = utc_now_iso()
    step_result: Dict[str, Any] = {
        "status": "pending",
        "started_at_utc": started_at_utc,
        "finished_at_utc": None,
        "duration_seconds": None,
        "total_products_processed": 0,
        "total_products_created_success": 0,
        "total_products_created_error": 0,
        "file_results_updated": [],  # List[FileResult]
        "error": None,
    }
    
    t0 = time.time()
    
    try:
        if not dynamo_client:
            step_result["status"] = "skipped"
            step_result["error"] = "DynamoServiceClient not available"
            return {
                "success": True,
                "step_result": step_result,
            }
        
        # Process each file's products
        for file_result in file_results:
            file_result_updated: FileResult = cast(FileResult, dict(file_result))
            products = file_result.get("products")
            
            if not products:
                file_result_updated["products_created_success"] = 0
                file_result_updated["products_created_error"] = 0
                file_result_updated["product_creation_errors"] = None
                step_result["file_results_updated"].append(file_result_updated)
                continue
            
            # Create products via API (pass file_result for supplier context)
            success_count, error_count, error_messages = create_products_from_list(
                dynamo_client, products, file_result
            )
            
            file_result_updated["products_created_success"] = success_count
            file_result_updated["products_created_error"] = error_count
            if error_messages:
                file_result_updated["product_creation_errors"] = error_messages
            else:
                file_result_updated["product_creation_errors"] = None
            
            step_result["file_results_updated"].append(file_result_updated)
            step_result["total_products_processed"] += len(products)
            step_result["total_products_created_success"] += success_count
            step_result["total_products_created_error"] += error_count
        
        step_result["status"] = "ok"
        
    except Exception as ex:
        step_result["status"] = "error"
        step_result["error"] = str(ex)
    
    finally:
        step_result["finished_at_utc"] = utc_now_iso()
        step_result["duration_seconds"] = round(time.time() - t0, 3)
    
    return {
        "success": step_result["status"] in ("ok", "skipped"),
        "step_result": step_result,
    }
