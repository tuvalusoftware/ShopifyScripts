#!/usr/bin/env python3
"""Step 4: Create products via DynamoServiceClient API."""
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


def utc_now_iso() -> str:
    """Get current UTC time as ISO string."""
    return datetime.now(timezone.utc).isoformat()


def create_products_from_list(
    dynamo_client,
    products: List[Dict[str, Any]],
) -> Tuple[int, int, List[str]]:
    """Create products via DynamoServiceClient API."""
    success_count = 0
    error_count = 0
    error_messages = []
    
    for product in products:
        try:
            # Convert product dict to properties format
            properties = {k: v for k, v in product.items() if v is not None}
            
            if not properties:
                error_count += 1
                error_messages.append("Product has no properties")
                continue
            
            # Call API to create product
            dynamo_client.create_product(properties=properties)
            success_count += 1
        except Exception as ex:
            error_count += 1
            error_msg = f"Failed to create product '{product.get('product_name', 'unknown')}': {str(ex)}"
            error_messages.append(error_msg)
    
    return success_count, error_count, error_messages


def execute(
    dynamo_client: Optional[Any],
    file_results: List[Dict[str, Any]],
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
        "file_results_updated": [],
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
            file_result_updated = file_result.copy()
            products = file_result.get("products")
            
            if not products:
                file_result_updated["products_created_success"] = 0
                file_result_updated["products_created_error"] = 0
                file_result_updated["product_creation_errors"] = None
                step_result["file_results_updated"].append(file_result_updated)
                continue
            
            # Create products via API
            success_count, error_count, error_messages = create_products_from_list(
                dynamo_client, products
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
