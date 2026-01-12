"""
DynamoServiceClient - Service class for interacting with DynamoDB Service API.

This module provides a client for creating and managing products via the DynamoDB Service API.
The API base URL is configured via the DYNAMO_SERVICE_API_URL environment variable.
"""

import os
import sys
import json
import tempfile
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List, TypedDict
import requests
from requests.exceptions import RequestException, HTTPError
import boto3  # type: ignore
from botocore.exceptions import ClientError, BotoCoreError  # type: ignore

# Setup paths for imports from flow/utils
_current_dir = os.path.dirname(os.path.abspath(__file__))
_extracting_service_dir = os.path.join(_current_dir, "../..")
sys.path.insert(0, _extracting_service_dir)

from flow.utils.s3_utils import ensure_s3_bucket_exists  # type: ignore


# ============================================================================
# DTO Definitions for API Request/Response
# ============================================================================

# Use functional syntax for TypedDict to support fields with spaces
SupplierDTO = TypedDict(
    'SupplierDTO',
    {
        'sender_email': Optional[str],
        'sender_name': Optional[str],
        'merchant': Optional[str],
        'currency_code': Optional[str],
        'delivery_data': Optional[str],
        'products': Optional[List[Dict[str, Any]]],
    },
    total=False
)


class ProductRequestDTO(TypedDict, total=False):
    """
    DTO for product data in API request.
    
    This represents a single product with all its properties.
    Fields can include: product_name, style_number, availability, color,
    color_code, size, description, material, certifications, country_of_origin,
    retail_price, ws_price, RPR, net_price, quantity_ordered, units,
    totalL_pieces, family, total, etc.
    """
    product_name: Optional[str]
    style_number: Optional[str]
    availability: Optional[str]
    color: Optional[str]
    color_code: Optional[str]
    size: Optional[str]
    season: Optional[str]
    description: Optional[str]
    material: Optional[str]
    certifications: Optional[str]
    country_of_origin: Optional[str]
    retail_price: Optional[str]
    ws_price: Optional[str]
    RPR: Optional[str]
    quantity_ordered: Optional[str]
    style_id: Optional[str]
    units: Optional[str]
    unit_price: Optional[str]
    totalL_pieces: Optional[str]
    family: Optional[str]
    net_price: Optional[str]
    list_price: Optional[str]
    discount: Optional[str]
    total: Optional[str]


class CreateProductRequestDTO(TypedDict, total=False):
    """
    DTO for complete API request payload.
    
    This represents the full structure expected by the API:
    {
        "shop_domain": "store.myshopify.com",
        "supplier": {
            "sender_email": "...",
            "sender_name": "...",
            "merchant": "...",
            "currency_code": "USD",
            "delivery_data": "...",
            "products": [...]
        }
    }
    
    Fields:
        shop_domain: Shopify store domain
        supplier: Supplier information DTO (contains products inside)
    """
    shop_domain: Optional[str]
    supplier: Optional[SupplierDTO]


class DynamoServiceClient:
    """
    Client for interacting with DynamoDB Service API.
    
    The API base URL is read from the DYNAMO_SERVICE_API_URL environment variable.
    If not set, an error will be raised when attempting to make API calls.
    """
    
    def __init__(self, api_url: Optional[str] = None, s3_client: Any = None):
        """
        Initialize the DynamoServiceClient.
        
        Args:
            api_url: Optional API base URL. If not provided, will be read from
                    DYNAMO_SERVICE_API_URL environment variable.
            s3_client: Optional boto3 S3 client. If not provided, will be created
                      using AWS_REGION environment variable.
        
        Raises:
            ValueError: If api_url is not provided and DYNAMO_SERVICE_API_URL is not set.
        """
        api_url_value = api_url or os.getenv("DYNAMO_SERVICE_API_URL")
        if not api_url_value:
            raise ValueError(
                "API URL must be provided either as parameter or via "
                "DYNAMO_SERVICE_API_URL environment variable"
            )
        # Remove trailing slash if present
        self._api_url: str = api_url_value.rstrip("/")
        
        # Initialize S3 client for archiving payloads
        if s3_client is not None:
            self._s3_client: Any = s3_client
        else:
            aws_region = os.getenv("AWS_REGION", "ap-southeast-1")
            self._s3_client: Any = boto3.client("s3", region_name=aws_region)  # type: ignore
    
    def _save_payload_to_s3(self, payload: Dict[str, Any], prefix: str = "payload") -> str:
        """
        Save payload to S3 archive bucket for debugging.
        
        Args:
            payload: The payload dictionary to save
            prefix: Prefix for the filename (default: "payload")
        
        Returns:
            S3 key path to the saved file
        
        Raises:
            ValueError: If ARCHIVE_BUCKET environment variable is not set.
        """
        archive_bucket = os.getenv("ARCHIVE_BUCKET")
        if not archive_bucket:
            raise ValueError(
                "ARCHIVE_BUCKET environment variable must be set to save payloads to S3"
            )
        
        aws_region = os.getenv("AWS_REGION", "ap-southeast-1")
        
        # Generate unique filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        filename = f"{prefix}_{timestamp}_{unique_id}.json"
        s3_key = f"archived_json_payloads/{filename}"
        
        try:
            # Check if archive bucket exists, create if not
            if not ensure_s3_bucket_exists(self._s3_client, archive_bucket, aws_region):
                raise ValueError(f"Failed to access or create archive bucket '{archive_bucket}'")
            
            # Convert payload to JSON string
            json_content = json.dumps(payload, indent=2, ensure_ascii=False)
            
            # Upload to S3
            self._s3_client.put_object(
                Bucket=archive_bucket,
                Key=s3_key,
                Body=json_content.encode('utf-8'),
                ContentType='application/json'
            )
            
            s3_path = f"s3://{archive_bucket}/{s3_key}"
            print(f"Payload saved to S3: {s3_path}")
            return s3_path
            
        except (ClientError, BotoCoreError) as e:
            raise ValueError(f"Failed to save payload to S3: {str(e)}") from e
    
    def create_product(
        self,
        properties: Dict[str, Any],
        shop_domain: Optional[str] = None,
        supplier: Optional[SupplierDTO] = None,
    ) -> Dict[str, Any]:
        """
        Create a new product via the DynamoDB Service API.
        
        The method supports two payload formats:
        1. Enhanced Format (if shop_domain or supplier provided):
           {
               "shop_domain": "...",
               "supplier": {
                   ...,
                   "products": [...]
               }
           }
        2. Legacy Format (Format 2: Direct Products Format):
           {"products": [...]}
        
        Args:
            properties: Required dictionary containing product properties.
                       Should include fields like: product_name, style_number,
                       availability, color, color_code, size, description, material,
                       certifications, country_of_origin, retail_price, ws_price,
                       RPR, net_price, quantity_ordered, units, totalL_pieces,
                       family, total, etc.
            shop_domain: Optional Shopify store domain (e.g., "store.myshopify.com").
                        If provided, will use enhanced format.
            supplier: Optional supplier information DTO. If provided, will use enhanced format.
        
        Returns:
            Dict containing the API response with import summary:
            {
                "success": bool,
                "message": str,
                "total": int,
                "imported": int,
                "failed": int,
                "errors": list,
                "sample_products": list
            }
        
        Raises:
            ValueError: If properties is empty or None.
            RequestException: If the HTTP request fails.
            HTTPError: If the API returns an error status code.
        """
        if not properties:
            raise ValueError("properties is required and cannot be empty")
        
        # Build request payload
        # Use enhanced format if shop_domain or supplier is provided
        if shop_domain or supplier:
            payload: Dict[str, Any] = {}
            if shop_domain:
                payload["shop_domain"] = shop_domain
            if supplier:
                # Create supplier dict with products inside
                supplier_with_products = dict(supplier) if supplier else {}
                supplier_with_products["products"] = [properties]
                payload["supplier"] = supplier_with_products
            else:
                # If only shop_domain provided, create empty supplier with products
                payload["supplier"] = {"products": [properties]}
        else:
            # Legacy format (Format 2: Direct Products Format)
            payload: Dict[str, Any] = {
                "products": [properties]
            }
        
        # Check if DEV_TEST_SCHEMA flag is enabled
        dev_test_schema = os.getenv("DEV_TEST_SCHEMA", "").lower() in ("true", "1", "yes", "on")
        
        if dev_test_schema:
            # In test mode, just log the JSON payload and return mock response
            json_payload = json.dumps(payload, indent=2)
            print("=" * 80)
            print("DEV_TEST_SCHEMA is enabled - Skipping API call")
            print("=" * 80)
            print("Product JSON payload:")
            print(json_payload)
            print("=" * 80)
            
            # Return mock response
            return {
                "success": True,
                "message": "DEV_TEST_SCHEMA mode: API call skipped, payload logged",
                "total": 1,
                "imported": 1,
                "failed": 0,
                "errors": [],
                "sample_products": [properties]
            }
        
        # Save payload to S3 archive bucket for debugging (prod mode)
        try:
            payload_s3_path = self._save_payload_to_s3(payload, prefix="payload_single")
            print(f"Payload file saved for debugging: {payload_s3_path}")
        except ValueError as e:
            # If ARCHIVE_BUCKET is not set, log warning but continue
            print(f"WARNING: Could not save payload to S3: {e}")
        
        # Make POST request to /data/insert endpoint with multipart/form-data
        url = f"{self._api_url}/data/insert"
        # log the payload
        print(f"Payload: {payload}")
        print(f"URL: {url}")
        
        # Create temporary JSON file for API upload
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tmp_file:
            json.dump(payload, tmp_file, indent=2)
            tmp_file_path = tmp_file.name
        
        try:
            # Upload file as multipart/form-data
            with open(tmp_file_path, 'rb') as f:
                files = {'file': ('merged.json', f, 'application/json')}
                response = requests.post(
                    url,
                    files=files,
                    timeout=30
                )
                response.raise_for_status()
                result = response.json()
                print(f"API Result: {json.dumps(result, indent=2)}")
                return result
        except HTTPError as e:
            # Try to extract error details from response
            if hasattr(e, 'response') and e.response is not None:
                error_msg = f"API request failed with status {e.response.status_code}"
                try:
                    error_detail = e.response.json()
                    error_msg = f"{error_msg}: {error_detail}"
                except Exception:
                    error_msg = f"{error_msg}: {e.response.text}"
            else:
                error_msg = f"API request failed: {str(e)}"
            raise HTTPError(error_msg) from e
        except RequestException as e:
            raise RequestException(f"Failed to create product: {str(e)}") from e
        finally:
            # Clean up temporary file (payload file is kept for debugging)
            try:
                os.unlink(tmp_file_path)
            except Exception:
                pass
    
    def create_products_batch(
        self,
        products: List[Dict[str, Any]],
        shop_domain: Optional[str] = None,
        supplier: Optional[SupplierDTO] = None,
    ) -> Dict[str, Any]:
        """
        Create multiple products via the DynamoDB Service API in a single batch request.
        
        The method supports two payload formats:
        1. Enhanced Format (if shop_domain or supplier provided):
           {
               "shop_domain": "...",
               "supplier": {
                   ...,
                   "products": [...]
               }
           }
        2. Legacy Format (Format 2: Direct Products Format):
           {"products": [...]}
        
        Args:
            products: Required list of product dictionaries. Each dictionary should
                    include fields like: product_name, style_number, availability,
                    color, color_code, size, description, material, certifications,
                    country_of_origin, retail_price, ws_price, RPR, net_price,
                    quantity_ordered, units, totalL_pieces, family, total, etc.
            shop_domain: Optional Shopify store domain (e.g., "store.myshopify.com").
                        If provided, will use enhanced format.
            supplier: Optional supplier information DTO. If provided, will use enhanced format.
        
        Returns:
            Dict containing the API response with import summary:
            {
                "success": bool,
                "message": str,
                "total": int,
                "imported": int,
                "failed": int,
                "errors": list,
                "sample_products": list
            }
        
        Raises:
            ValueError: If products list is empty or None.
            RequestException: If the HTTP request fails.
            HTTPError: If the API returns an error status code.
        """
        if not products:
            raise ValueError("products list is required and cannot be empty")
        
        # Build request payload
        # Use enhanced format if shop_domain or supplier is provided
        if shop_domain or supplier:
            payload: Dict[str, Any] = {}
            if shop_domain:
                payload["shop_domain"] = shop_domain
            if supplier:
                # Create supplier dict with products inside
                supplier_with_products = dict(supplier) if supplier else {}
                supplier_with_products["products"] = products
                payload["supplier"] = supplier_with_products
            else:
                # If only shop_domain provided, create empty supplier with products
                payload["supplier"] = {"products": products}
        else:
            # Legacy format (Format 2: Direct Products Format)
            payload: Dict[str, Any] = {
                "products": products
            }
        
        # Check if DEV_TEST_SCHEMA flag is enabled
        dev_test_schema = os.getenv("DEV_TEST_SCHEMA", "").lower() in ("true", "1", "yes", "on")
        
        if dev_test_schema:
            # In test mode, just log the JSON payload and return mock response
            json_payload = json.dumps(payload, indent=2)
            print("=" * 80)
            print("DEV_TEST_SCHEMA is enabled - Skipping API call")
            print("=" * 80)
            print(f"Batch Product JSON payload ({len(products)} products):")
            print(json_payload)
            print("=" * 80)
            
            # Return mock response
            return {
                "success": True,
                "message": f"DEV_TEST_SCHEMA mode: API call skipped, payload logged ({len(products)} products)",
                "total": len(products),
                "imported": len(products),
                "failed": 0,
                "errors": [],
                "sample_products": products[:5]  # Return first 5 as sample
            }
        
        # Save payload to S3 archive bucket for debugging (prod mode)
        try:
            payload_s3_path = self._save_payload_to_s3(payload, prefix="payload_batch")
            print(f"Payload file saved for debugging: {payload_s3_path}")
        except ValueError as e:
            # If ARCHIVE_BUCKET is not set, log warning but continue
            print(f"WARNING: Could not save payload to S3: {e}")
        
        # Make POST request to /data/insert endpoint with multipart/form-data
        url = f"{self._api_url}/data/insert"
        # log the payload
        print(f"Batch Payload: {len(products)} products")
        print(f"URL: {url}")
        
        # Create temporary JSON file for API upload
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tmp_file:
            json.dump(payload, tmp_file, indent=2)
            tmp_file_path = tmp_file.name
        
        try:
            # Upload file as multipart/form-data
            with open(tmp_file_path, 'rb') as f:
                files = {'file': ('merged.json', f, 'application/json')}
                response = requests.post(
                    url,
                    files=files,
                    timeout=30
                )
                response.raise_for_status()
                result = response.json()
                print(f"API Result: {json.dumps(result, indent=2)}")
                return result
        except HTTPError as e:
            # Try to extract error details from response
            if hasattr(e, 'response') and e.response is not None:
                error_msg = f"API request failed with status {e.response.status_code}"
                try:
                    error_detail = e.response.json()
                    error_msg = f"{error_msg}: {error_detail}"
                except Exception:
                    error_msg = f"{error_msg}: {e.response.text}"
            else:
                error_msg = f"API request failed: {str(e)}"
            raise HTTPError(error_msg) from e
        except RequestException as e:
            raise RequestException(f"Failed to create products batch: {str(e)}") from e
        finally:
            # Clean up temporary file (payload file is kept for debugging)
            try:
                os.unlink(tmp_file_path)
            except Exception:
                pass
    
    def get_api_url(self) -> str:
        """
        Get the configured API base URL.
        
        Returns:
            The API base URL string.
        """
        return self._api_url

