#!/usr/bin/env python3
"""Step 3: Process a single file - upload, call model, parse products."""
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI

# Setup paths for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
import _path_setup  # noqa: F401

from utils.logger import get_logger

# Setup logger
logger = get_logger(__name__)


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


def utc_now_iso() -> str:
    """Get current UTC time as ISO string."""
    return datetime.now(timezone.utc).isoformat()


def upload_file(client: OpenAI, path: Path, purpose: str = "assistants") -> str:
    """Upload a file and return file_id."""
    with path.open("rb") as f:
        resp = client.files.create(file=f, purpose=purpose)
    return resp.id


def call_responses_with_file(
    client: OpenAI,
    model: str,
    prompt: str,
    file_id: str,
    filename: str,
    max_output_tokens: int,
) -> str:
    """Use Responses API with an input_file."""
    resp = client.responses.create(
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
        for item in resp.output:
            if getattr(item, "type", None) == "message":
                for c in item.content:
                    if getattr(c, "type", None) in ("output_text", "text"):
                        chunks.append(getattr(c, "text", "") or "")
    except Exception:
        pass
    
    return "\n".join([c for c in chunks if c]).strip()


def parse_products_from_response(response_text: str) -> List[Dict[str, Any]]:
    """Parse products from OpenAI response text."""
    if not response_text:
        return []
    
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
        result = json.loads(response_text)
        if isinstance(result, dict) and "products" in result:
            return result.get("products", [])
        elif isinstance(result, list):
            return result
        else:
            return []
    except json.JSONDecodeError:
        return []


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
            mapping = json.load(f)
            # Validate structure
            if isinstance(mapping, dict):
                return mapping
            return {}
    except Exception as e:
        logger.warning(f"WARNING: Failed to load sender mapping file {mapping_file_path}: {e}")
        return {}


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
    prefix = extract_prefix_from_filename(filename)
    
    # Lookup sender info from mapping
    sender_email, sender_name = get_sender_info_from_mapping(prefix, sender_mapping)
    
    # Create new list with enriched products
    enriched_products = []
    for product in products:
        enriched_product = product.copy()
        enriched_product["sender_email"] = sender_email
        enriched_product["sender_name"] = sender_name
        enriched_products.append(enriched_product)
    
    return enriched_products


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


def execute(
    openai_client: OpenAI,
    file_path: str,
    prompt: str,
    model: str,
    max_output_tokens: int,
    upload_purpose: str = "assistants",
    sender_mapping_file: Optional[str] = None,
) -> Dict[str, Any]:
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
        Dict with 'success' bool and processing results or 'error' message
    """
    started_at_utc = utc_now_iso()
    t0 = time.time()
    
    # Initialize result structure
    file_result: Dict[str, Any] = {
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
    }
    
    try:
        # ===== SIDE EFFECTS: Load external data =====
        # Load file metadata from file system
        file_metadata = load_file_metadata(file_path)
        file_result["input_name"] = file_metadata["name"]
        file_result["input_size_bytes"] = file_metadata["size_bytes"]
        
        # Load sender mapping from file system (if provided)
        sender_mapping: Dict[str, Dict[str, str]] = {}
        if sender_mapping_file:
            sender_mapping = load_sender_mapping(sender_mapping_file)
        
        # ===== SIDE EFFECTS: File operations =====
        path = Path(file_path)
        file_result["input_sha256"] = sha256_file(path)
        
        # ===== SIDE EFFECTS: API calls =====
        # Upload file to OpenAI
        file_id = upload_file(openai_client, path, purpose=upload_purpose)
        file_result["uploaded_file_id"] = file_id
        
        # Call OpenAI API
        response_text = call_responses_with_file(
            client=openai_client,
            model=model,
            prompt=prompt,
            file_id=file_id,
            filename=file_result["input_name"],
            max_output_tokens=max_output_tokens,
        )
        
        # ===== PURE LOGIC: Parse and transform data =====
        # Parse products from API response (pure function)
        products = parse_products_from_response(response_text)
        
        # Enrich products with sender info (pure function)
        enriched_products = enrich_products_with_sender_info(
            products=products,
            filename=file_result["input_name"],
            sender_mapping=sender_mapping
        )
        
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
        file_result["finished_at_utc"] = utc_now_iso()
        file_result["duration_seconds"] = round(time.time() - t0, 3)
    
    return {
        "success": file_result["status"] == "ok",
        "file_result": file_result,
    }
