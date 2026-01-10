#!/usr/bin/env python3
"""Step 6: Extract products from attachments."""
import os
import sys
import subprocess
import traceback
from typing import Any, Dict, Optional
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

# Import directory manager
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from utils.directory_manager import DirectoryManager


def execute(
    dir_manager: DirectoryManager,
    prompt_file: str,
    extraction_out_dir: str,
    script_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Call flow2.py to process attachments.
    
    Args:
        dir_manager: DirectoryManager instance
        prompt_file: Path to prompt file for extraction
        extraction_out_dir: Output directory for extraction results
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
