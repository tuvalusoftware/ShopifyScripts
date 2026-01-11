#!/usr/bin/env python3
"""Step 1: Initialize OpenAI client, DynamoServiceClient, read prompt."""
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from openai import OpenAI

# Setup paths for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
import _path_setup  # noqa: F401

from domain.DynamoServiceClient import DynamoServiceClient
from utils.directory_manager import DirectoryManager


def read_text_file(path: Path) -> str:
    """Read text file and return content."""
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    if not text:
        raise ValueError(f"File is empty after trimming: {path}")
    return text


def execute(
    dir_manager: DirectoryManager,
    prompt_file: str,
) -> Dict[str, Any]:
    """
    Initialize OpenAI client, DynamoServiceClient, read prompt.
    
    Args:
        dir_manager: DirectoryManager instance
        prompt_file: Path to prompt file
        
    Returns:
        Dict with 'success' bool and initialized objects or 'error' message
    """
    try:
        # Check OpenAI API key
        if not os.environ.get("OPENAI_API_KEY"):
            return {
                "success": False,
                "error": "OPENAI_API_KEY is not set",
            }
        
        # Initialize OpenAI client
        openai_client = OpenAI()
        
        # Initialize DynamoServiceClient (optional)
        dynamo_client = None
        try:
            dynamo_client = DynamoServiceClient()
        except ValueError:
            # DynamoServiceClient not available, continue without it
            pass
        
        # Read prompt file
        prompt_path = Path(prompt_file).expanduser().resolve()
        prompt = read_text_file(prompt_path)
        
        return {
            "success": True,
            "openai_client": openai_client,
            "dynamo_client": dynamo_client,
            "prompt": prompt,
            "prompt_path": str(prompt_path),
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }
