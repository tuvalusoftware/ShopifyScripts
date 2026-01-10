#!/usr/bin/env python3
"""Step 3: Process a single file - upload, call model, parse products, write response."""
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from openai import OpenAI

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

# Import directory manager
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from utils.directory_manager import DirectoryManager


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


def safe_stem(name: str) -> str:
    """Make filesystem-safe stem from filename."""
    stem = re.sub(r"[^\w\-\.]+", "_", name.strip(), flags=re.UNICODE)
    stem = re.sub(r"_+", "_", stem).strip("._-")
    return stem or "file"


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


def write_text(path: Path, text: str) -> None:
    """Write text to file."""
    path.write_text(text, encoding="utf-8")


def execute(
    dir_manager: DirectoryManager,
    openai_client: OpenAI,
    file_path: str,
    file_name: str,
    file_size_bytes: int,
    prompt: str,
    model: str,
    max_output_tokens: int,
    response_ext: str,
    upload_purpose: str = "assistants",
) -> Dict[str, Any]:
    """
    Process a single file: upload, call model, parse products, write response.
    
    Args:
        dir_manager: DirectoryManager instance
        openai_client: OpenAI client instance
        file_path: Path to input file
        file_name: Name of input file
        file_size_bytes: Size of input file in bytes
        prompt: Prompt text for model
        model: Model name
        max_output_tokens: Maximum output tokens
        response_ext: Extension for response files
        upload_purpose: OpenAI file upload purpose
        
    Returns:
        Dict with 'success' bool and processing results or 'error' message
    """
    started_at_utc = utc_now_iso()
    file_result: Dict[str, Any] = {
        "input_path": file_path,
        "input_name": file_name,
        "input_size_bytes": file_size_bytes,
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
    
    t0 = time.time()
    
    try:
        path = Path(file_path)
        
        # Calculate SHA256
        file_result["input_sha256"] = sha256_file(path)
        
        # Upload file
        file_id = upload_file(openai_client, path, purpose=upload_purpose)
        file_result["uploaded_file_id"] = file_id
        
        # Call model
        response_text = call_responses_with_file(
            client=openai_client,
            model=model,
            prompt=prompt,
            file_id=file_id,
            filename=file_name,
            max_output_tokens=max_output_tokens,
        )
        
        # Write response file
        base = safe_stem(path.stem)
        short_hash = file_result["input_sha256"][:12] if file_result["input_sha256"] else "nohash"
        resp_ext = response_ext if response_ext.startswith(".") else "." + response_ext
        resp_name = f"{base}__{short_hash}{resp_ext}"
        responses_dir = dir_manager.get_responses_dir()
        resp_path = Path(responses_dir) / resp_name
        write_text(resp_path, response_text)
        file_result["response_path"] = str(resp_path)
        
        # Parse products from response
        products = parse_products_from_response(response_text)
        file_result["products_extracted"] = len(products)
        if products:
            file_result["products"] = products
        
        file_result["status"] = "ok"
        
    except Exception as ex:
        file_result["status"] = "error"
        file_result["error"] = str(ex)
    
    finally:
        file_result["finished_at_utc"] = utc_now_iso()
        file_result["duration_seconds"] = round(time.time() - t0, 3)
    
    return {
        "success": file_result["status"] == "ok",
        "file_result": file_result,
    }
