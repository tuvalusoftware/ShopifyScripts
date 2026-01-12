#!/usr/bin/env python3
"""Step3Util: Utility class for processing files with LLM."""
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple, cast

from openai import OpenAI
import sys

# Setup paths for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from utils.logger import get_logger

# Setup logger
logger = get_logger(__name__)


class Step3Util:
    """Utility class for processing files with LLM."""
    
    def __init__(self, openai_client: OpenAI):
        """
        Initialize Step3Util with OpenAI client.
        
        Args:
            openai_client: OpenAI client instance
        """
        self.openai_client = openai_client
    
    @staticmethod
    def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
        """Calculate SHA256 hash of file."""
        h = hashlib.sha256()
        with path.open("rb") as f:
            while True:
                b = f.read(chunk_size)
                if not b:
                    break
                h.update(b)
        return h.hexdigest()
    
    @staticmethod
    def utc_now_iso() -> str:
        """Get current UTC time as ISO string."""
        return datetime.now(timezone.utc).isoformat()
    
    def upload_file(
        self,
        path: Path,
        purpose: Literal["assistants", "batch", "fine-tune", "vision", "user_data", "evals"] = "assistants"
    ) -> str:
        """Upload a file and return file_id."""
        with path.open("rb") as f:
            resp = self.openai_client.files.create(file=f, purpose=purpose)
        return resp.id
    
    def call_responses_with_file(
        self,
        model: str,
        prompt: str,
        file_id: str,
        filename: str,
        max_output_tokens: int,
    ) -> str:
        """Use Responses API with an input_file."""
        resp = self.openai_client.responses.create(
            model=model,
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {"type": "input_text", "text": f"\n\nProcessing file: {filename}"},
                        {"type": "input_file", "file_id": file_id},
                    ],
                }
            ],
            max_output_tokens=max_output_tokens,
        )
        
        # Extract response text
        if hasattr(resp, "output_text") and resp.output_text:
            return resp.output_text
        
        # Fallback extraction
        chunks: List[str] = []
        try:
            if hasattr(resp, "output") and resp.output:
                for item in resp.output:
                    if hasattr(item, "type") and getattr(item, "type", None) == "message":
                        if hasattr(item, "content") and item.content:  # type: ignore[attr-defined]
                            for c in item.content:  # type: ignore[attr-defined]
                                c_type = getattr(c, "type", None)  # type: ignore[arg-type]
                                if c_type in ("output_text", "text"):
                                    text_value = getattr(c, "text", "")  # type: ignore[attr-defined,arg-type]
                                    if text_value:
                                        chunks.append(str(text_value))
        except Exception:
            pass
        
        return "\n".join(chunks).strip()
    
    @staticmethod
    def convert_raw_product_to_product(raw_product: Any) -> Dict[str, Any]:
        """Convert raw product dictionary to Product format.
        
        This function handles:
        - Preserving all fields including those with spaces
        - Keeping all values as strings (per prompt specification)
        
        Args:
            raw_product: Raw product dictionary from OpenAI response
            
        Returns:
            Product dictionary with preserved string types
        """
        product_dict: Dict[str, Any] = {}
        
        # Convert to dict if needed
        if not isinstance(raw_product, dict):
            return {}
        
        # Cast to Dict for type checking
        raw_dict: Dict[str, Any] = cast(Dict[str, Any], raw_product)
        
        # Copy all fields from raw_product, preserving field names and values as-is
        for key, value in raw_dict.items():
            if value is not None:
                product_dict[key] = value
        
        return product_dict
    
    @staticmethod
    def parse_openai_raw_response(response_text: str) -> Optional[Dict[str, Any]]:
        """Parse raw OpenAI response text into typed structure.
        
        Args:
            response_text: Raw text response from OpenAI API
            
        Returns:
            Dict if parsing succeeds, None otherwise
        """
        if not response_text:
            return None
        
        # Try to extract JSON from markdown code blocks
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response_text, re.DOTALL)
        if json_match:
            response_text = json_match.group(1)
        else:
            # Try to find JSON object directly
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                response_text = json_match.group(0)
        
        try:
            result: Any = json.loads(response_text)
            if isinstance(result, dict):
                return cast(Dict[str, Any], result)
            return None
        except json.JSONDecodeError:
            return None
    
    @staticmethod
    def get_shipper_from_response(response_text: str) -> Optional[Dict[str, Any]]:
        """Extract SHIPPER data from OpenAI response.
        
        Args:
            response_text: Raw text response from OpenAI API
            
        Returns:
            Dict if found, None otherwise
        """
        raw_response = Step3Util.parse_openai_raw_response(response_text)
        if raw_response and "SHIPPER" in raw_response:
            return raw_response["SHIPPER"]
        return None
    
    @staticmethod
    def parse_products_from_response(response_text: str) -> List[Dict[str, Any]]:
        """Parse products from OpenAI response text.
        
        This function parses the raw OpenAI response and converts it to
        a list of Product objects, handling fields with spaces in names.
        
        Args:
            response_text: Raw text response from OpenAI API
            
        Returns:
            List of Product dictionaries
        """
        if not response_text:
            return []
        
        # Parse raw response
        raw_response = Step3Util.parse_openai_raw_response(response_text)
        if not raw_response:
            return []
        
        products: List[Dict[str, Any]] = []
        
        # Extract products from raw response
        if "products" in raw_response and raw_response["products"]:
            for raw_product in raw_response["products"]:
                product = Step3Util.convert_raw_product_to_product(raw_product)
                products.append(product)
        
        # Also handle case where response is directly a list of products
        elif "products" not in raw_response:
            # Try to parse as list directly
            try:
                result: Any = json.loads(response_text)
                if isinstance(result, list):
                    raw_products_list: List[Dict[str, Any]] = cast(List[Dict[str, Any]], result)
                    for raw_product in raw_products_list:
                        product = Step3Util.convert_raw_product_to_product(raw_product)
                        products.append(product)
            except (json.JSONDecodeError, TypeError):
                pass
        
        return products
    
    @staticmethod
    def load_sender_mapping(mapping_file_path: Optional[str]) -> Dict[str, Dict[str, str]]:
        """
        Load sender mapping from JSON file.
        
        Args:
            mapping_file_path: Path to sender_mapping.json file
            
        Returns:
            Dict mapping prefix -> {sender_email, sender_name}, empty dict if file not found or error
        """
        if not mapping_file_path or not os.path.exists(mapping_file_path):
            return {}
        
        try:
            with open(mapping_file_path, "r", encoding="utf-8") as f:
                mapping: Any = json.load(f)
                # Validate structure
                if isinstance(mapping, dict):
                    return cast(Dict[str, Dict[str, str]], mapping)
                return {}
        except Exception as e:
            logger.warning(f"WARNING: Failed to load sender mapping file {mapping_file_path}: {e}")
            return {}
    
    @staticmethod
    def extract_prefix_from_filename(filename: str) -> Optional[str]:
        """
        Extract prefix from attachment filename.
        
        Format: {prefix}_{idx:02d}_{fname}
        Example: eml0001_01_file.pdf -> eml0001
        
        Args:
            filename: Filename to extract prefix from
            
        Returns:
            Prefix string or None if pattern doesn't match
        """
        # Match pattern: prefix_XX_filename
        match = re.match(r'^([a-zA-Z0-9]+)_\d{2}_', filename)
        if match:
            return match.group(1)
        return None
    
    @staticmethod
    def get_sender_info_from_mapping(
        prefix: Optional[str],
        sender_mapping: Dict[str, Dict[str, str]]
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Get sender email and name from mapping based on prefix.
        
        Pure function - no side effects.
        
        Args:
            prefix: Prefix extracted from filename
            sender_mapping: Mapping dict from prefix to sender info
            
        Returns:
            Tuple of (sender_email, sender_name), both can be None
        """
        if not prefix or not sender_mapping:
            return None, None
        
        sender_info = sender_mapping.get(prefix)
        if not sender_info:
            return None, None
        
        sender_email = sender_info.get("sender_email") or None
        sender_name = sender_info.get("sender_name") or None
        return sender_email, sender_name
    
    @staticmethod
    def enrich_products_with_sender_info(
        products: List[Dict[str, Any]],
        filename: str,
        sender_mapping: Dict[str, Dict[str, str]]
    ) -> List[Dict[str, Any]]:
        """
        Enrich products with sender information based on filename prefix.
        
        Pure function - no side effects, returns new list with enriched products.
        
        Args:
            products: List of product dictionaries
            filename: Filename to extract prefix from
            sender_mapping: Mapping dict from prefix to sender info
            
        Returns:
            New list of products with sender_email and sender_name fields added
        """
        if not products:
            return products
        
        # Extract prefix from filename
        prefix = Step3Util.extract_prefix_from_filename(filename)
        
        # Lookup sender info from mapping
        sender_email, sender_name = Step3Util.get_sender_info_from_mapping(prefix, sender_mapping)
        
        # Create new list with enriched products
        enriched_products: List[Dict[str, Any]] = []
        for product in products:
            # Create new dict with enriched fields
            enriched_product_dict: Dict[str, Any] = dict(product)
            enriched_product_dict["sender_email"] = sender_email
            enriched_product_dict["sender_name"] = sender_name
            enriched_products.append(enriched_product_dict)
        
        return enriched_products
    
    @staticmethod
    def load_file_metadata(file_path: str) -> Dict[str, Any]:
        """
        Load file metadata (name, size) from file system.
        
        Side effect: reads from file system.
        
        Args:
            file_path: Path to file
            
        Returns:
            Dict with 'name' and 'size_bytes' keys
            
        Raises:
            OSError: If file cannot be accessed
        """
        path = Path(file_path)
        return {
            "name": path.name,
            "size_bytes": path.stat().st_size,
        }
