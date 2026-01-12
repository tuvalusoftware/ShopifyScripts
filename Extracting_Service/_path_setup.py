#!/usr/bin/env python3
"""
Centralized path setup for Extracting_Service.

This module sets up Python path to allow imports from:
- Extracting_Service root (for parse_eml, domain modules)
- flow directory (for utils modules)

Import this module once at the top of your file:
    import _path_setup  # noqa: F401

The import itself triggers the path setup, so no function call is needed.
"""
import sys
from pathlib import Path


def _setup_paths() -> None:
    """
    Add Extracting_Service root and flow directory to sys.path.
    
    This allows imports like:
    - from parse_eml import parse_eml_file
    - from domain.DynamoServiceClient import DynamoServiceClient
    - from utils.directory_manager import DirectoryManager
    """
    # Get the directory where this file is located (Extracting_Service root)
    service_root = Path(__file__).parent.absolute()
    
    # Add service root to path if not already present
    service_root_str = str(service_root)
    if service_root_str not in sys.path:
        sys.path.insert(0, service_root_str)
    
    # Add flow directory to path if not already present
    flow_dir = service_root / "flow"
    flow_dir_str = str(flow_dir)
    if flow_dir_str not in sys.path:
        sys.path.insert(0, flow_dir_str)


# Automatically setup paths when module is imported
_setup_paths()
