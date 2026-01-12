#!/usr/bin/env python3
"""Step 6: Extract products from attachments."""
import os
import sys
import subprocess
import traceback
import json
import re
from typing import Any, Dict, List, Optional
from datetime import datetime

# Setup paths for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from utils.directory_manager import DirectoryManager
from utils.logger import get_logger

# Setup logger
logger = get_logger(__name__)


def extract_prefix_from_attachment_path(attachment_path: str) -> Optional[str]:
    """
    Extract prefix from attachment filename.
    
    Format: {prefix}_{idx:02d}_{fname}
    Example: eml0001_01_file.pdf -> eml0001
    
    Args:
        attachment_path: Full path or filename of attachment
        
    Returns:
        Prefix string or None if pattern doesn't match
    """
    filename = os.path.basename(attachment_path)
    # Match pattern: prefix_XX_filename
    match = re.match(r'^([a-zA-Z0-9]+)_\d{2}_', filename)
    if match:
        return match.group(1)
    return None


def create_sender_mapping_file(
    records: List[Dict[str, Any]],
    output_dir: str,
) -> Optional[str]:
    """
    Create sender mapping file from email records.
    
    Args:
        records: List of email records from flow1 step4 (contains sender_email, sender_name, attachments)
        output_dir: Directory where mapping file should be saved
        
    Returns:
        Path to created mapping file, or None if no records or error
    """
    if not records:
        return None
    
    mapping: Dict[str, Dict[str, str]] = {}
    
    for record in records:
        sender_email = record.get("sender_email", "")
        sender_name = record.get("sender_name", "")
        attachments = record.get("attachments", [])
        
        # Extract prefix from first attachment if available
        prefix = None
        if attachments:
            first_attachment = attachments[0]
            attachment_path = first_attachment.get("path", "")
            if attachment_path:
                prefix = extract_prefix_from_attachment_path(attachment_path)
        
        # If no prefix from attachments, try to extract from eml_path or other sources
        if not prefix:
            # Try to extract from eml_path if it contains prefix pattern
            eml_path = record.get("eml_path", "")
            if eml_path:
                # Check if path contains eml#### pattern
                match = re.search(r'(eml\d{4})', eml_path)
                if match:
                    prefix = match.group(1)
        
        # If still no prefix, skip this record
        if not prefix:
            continue
        
        # Store mapping
        mapping[prefix] = {
            "sender_email": sender_email or "",
            "sender_name": sender_name or "",
        }
    
    if not mapping:
        return None
    
    # Save mapping file
    mapping_file_path = os.path.join(output_dir, "sender_mapping.json")
    try:
        os.makedirs(output_dir, exist_ok=True)
        with open(mapping_file_path, "w", encoding="utf-8") as f:
            json.dump(mapping, f, ensure_ascii=False, indent=2)
        return mapping_file_path
    except Exception as e:
        logger.warning(f"WARNING: Failed to create sender mapping file: {e}")
        return None


def execute(
    dir_manager: DirectoryManager,
    prompt_file: str,
    extraction_out_dir: str,
    records: Optional[List[Dict[str, Any]]] = None,
    script_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Call flow2.py to process attachments.
    
    Args:
        dir_manager: DirectoryManager instance
        prompt_file: Path to prompt file for extraction
        extraction_out_dir: Output directory for extraction results
        records: Optional list of email records from flow1 step4 (for creating sender mapping)
        script_path: Optional path to extraction script (flow2.py)
        
    Returns:
        Dict with 'success' bool and optional 'error' message
    """
    if script_path is None:
        # Get path to flow2.py (flow/flow2/flow2.py relative to this file)
        script_path = os.path.join(os.path.dirname(__file__), "../flow2/flow2.py")
        script_path = os.path.normpath(script_path)
    
    if not os.path.exists(script_path):
        return {
            "success": False,
            "error": f"Flow2 script not found: {script_path}",
        }
    
    # Resolve prompt file path: if relative, resolve relative to script directory
    if not os.path.isabs(prompt_file):
        script_dir = os.path.join(os.path.dirname(__file__), "../..")
        prompt_file = os.path.join(script_dir, prompt_file)
        prompt_file = os.path.normpath(prompt_file)
    
    if not os.path.exists(prompt_file):
        return {
            "success": False,
            "error": f"Prompt file not found: {prompt_file}",
        }
    
    attachments_dir = dir_manager.get_attachments_dir()
    if not os.path.exists(attachments_dir):
        return {
            "success": False,
            "error": f"Attachments directory does not exist: {attachments_dir}",
        }
    
    # Create sender mapping file if records are provided
    sender_mapping_file = None
    if records:
        sender_mapping_file = create_sender_mapping_file(
            records=records,
            output_dir=extraction_out_dir,  # Save mapping file in extraction_out_dir
        )
        if sender_mapping_file:
            logger.info(f"Created sender mapping file: {sender_mapping_file}")
    
    # Check if there are any files in the attachments directory
    try:
        files_in_dir = [f for f in os.listdir(attachments_dir) if os.path.isfile(os.path.join(attachments_dir, f))]
        if not files_in_dir:
            return {
                "success": True,
                "skipped": True,
                "message": f"No files found in {attachments_dir}, skipping extraction",
            }
    except Exception as e:
        return {
            "success": False,
            "error": f"Error checking attachments directory: {e}",
        }
    
    # Create log file path in extraction output directory
    log_dir = dir_manager.get_extraction_log_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file_path = os.path.join(log_dir, f"extraction_{timestamp}.log")
    
    try:
        # Build command
        cmd = [
            sys.executable,
            script_path,
            "--attachment_dir", attachments_dir,
            "--prompt_file", prompt_file,
            "--out_dir", extraction_out_dir,
            "--no_run_subdir",  # Write directly to out_dir without run_* subdirectory
        ]
        
        # Add sender mapping file if available
        if sender_mapping_file and os.path.exists(sender_mapping_file):
            cmd.extend(["--sender_mapping_file", sender_mapping_file])
        
        # Run the script with captured output
        result = subprocess.run(
            cmd,
            capture_output=True,  # Capture stdout and stderr
            text=True,
        )
        
        # Write all output to log file
        with open(log_file_path, "w", encoding="utf-8") as log_file:
            log_file.write(f"=== Product Extraction Log (Flow2) ===\n")
            log_file.write(f"Started at: {datetime.now().isoformat()}\n")
            log_file.write(f"Command: {' '.join(cmd)}\n")
            log_file.write(f"Exit code: {result.returncode}\n")
            log_file.write(f"\n{'='*60}\n")
            log_file.write(f"STDOUT:\n")
            log_file.write(f"{'='*60}\n")
            if result.stdout:
                log_file.write(result.stdout)
            else:
                log_file.write("(no stdout output)\n")
            log_file.write(f"\n{'='*60}\n")
            log_file.write(f"STDERR:\n")
            log_file.write(f"{'='*60}\n")
            if result.stderr:
                log_file.write(result.stderr)
            else:
                log_file.write("(no stderr output)\n")
            log_file.write(f"\n{'='*60}\n")
            log_file.write(f"Finished at: {datetime.now().isoformat()}\n")
        
        if result.returncode == 0:
            return {
                "success": True,
                "log_file": log_file_path,
            }
        else:
            return {
                "success": False,
                "error": f"Extraction failed with exit code {result.returncode}",
                "log_file": log_file_path,
            }
            
    except Exception as e:
        error_msg = f"Error calling flow2 script: {e}"
        try:
            with open(log_file_path, "a", encoding="utf-8") as log_file:
                log_file.write(f"\n{error_msg}\n")
                log_file.write(traceback.format_exc())
        except Exception:
            pass  # If we can't write to log, at least we have the error
        return {
            "success": False,
            "error": error_msg,
        }
