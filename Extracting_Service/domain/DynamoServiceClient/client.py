"""
DynamoServiceClient - Service class for interacting with DynamoDB Service API.

This module provides a client for creating and managing products via the DynamoDB Service API.
The API base URL is configured via the DYNAMO_SERVICE_API_URL environment variable.
"""

import os
import json
import tempfile
from typing import Dict, Any, Optional
import requests
from requests.exceptions import RequestException, HTTPError


class DynamoServiceClient:
    """
    Client for interacting with DynamoDB Service API.
    
    The API base URL is read from the DYNAMO_SERVICE_API_URL environment variable.
    If not set, an error will be raised when attempting to make API calls.
    """
    
    def __init__(self, api_url: Optional[str] = None):
        """
        Initialize the DynamoServiceClient.
        
        Args:
            api_url: Optional API base URL. If not provided, will be read from
                    DYNAMO_SERVICE_API_URL environment variable.
        
        Raises:
            ValueError: If api_url is not provided and DYNAMO_SERVICE_API_URL is not set.
        """
        self._api_url = api_url or os.getenv("DYNAMO_SERVICE_API_URL")
        if not self._api_url:
            raise ValueError(
                "API URL must be provided either as parameter or via "
                "DYNAMO_SERVICE_API_URL environment variable"
            )
        # Remove trailing slash if present
        self._api_url = self._api_url.rstrip("/")
    
    def create_product(
        self,
        properties: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Create a new product via the DynamoDB Service API.
        
        The method sends the product in Format 2 (Direct Products Format):
        {"products": [product_properties]}
        
        Args:
            properties: Required dictionary containing product properties.
                       Should include fields like: product_name, style_number,
                       availability, color, color_code, size, description, material,
                       certifications, country_of_origin, retail_price, ws_price,
                       RPR, net_price, quantity_ordered, units, totalL_pieces,
                       family, total, etc.
        
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
        
        # Build request payload according to API format (Format 2: Direct Products Format)
        # The API expects: {"products": [...]}
        payload: Dict[str, Any] = {
            "products": [properties]
        }
        
        # Make POST request to /data/insert endpoint with multipart/form-data
        url = f"{self._api_url}/data/insert"
        # log the payload
        print(f"Payload: {payload}")
        print(f"URL: {url}")
        
        # Create temporary JSON file
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
            # Clean up temporary file
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

