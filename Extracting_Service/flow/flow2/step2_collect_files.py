#!/usr/bin/env python3
"""Step 2: Collect files from input directory."""
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


def normalize_exts(exts: Optional[List[str]]) -> Optional[Set]:
    """Normalize file extensions."""
    if not exts:
        return None
    norm = set()
    for e in exts:
        e = e.strip().lower()
        if not e:
            continue
        if not e.startswith("."):
            e = "." + e
        norm.add(e)
    return norm if norm else None


def iter_files(root: Path, exts: Optional[Set], recursive: bool) -> List[Path]:
    """
    Collect files from directory.
    
    Args:
        root: Root directory path
        exts: Set of allowed extensions (None = all)
        recursive: Whether to recurse into subdirectories
        
    Returns:
        List of file paths
    """
    if not root.exists():
        raise FileNotFoundError(f"Directory not found: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Not a directory: {root}")
    
    files: List[Path] = []
    it = root.rglob("*") if recursive else root.iterdir()
    for p in sorted(it):
        if not p.is_file():
            continue
        if exts is not None and p.suffix.lower() not in exts:
            continue
        files.append(p)
    
    return files


def execute(
    input_dir: str,
    exts: Optional[List[str]] = None,
    recursive: bool = False,
    max_files: int = 50,
    max_bytes: int = 20000000,
) -> Dict[str, Any]:
    """
    Collect files from input directory.
    
    Args:
        input_dir: Input directory path
        exts: List of file extensions to include (None = all)
        recursive: Whether to recurse into subdirectories
        max_files: Maximum number of files to collect
        max_bytes: Maximum file size in bytes
        
    Returns:
        Dict with 'success' bool and 'files' list or 'error' message
    """
    try:
        input_dir_path = Path(input_dir).expanduser().resolve()
        normalized_exts = normalize_exts(exts)
        
        all_files = iter_files(input_dir_path, normalized_exts, recursive)
        
        # Filter by max_files and max_bytes
        files: List[Dict[str, Any]] = []
        for p in all_files[:max_files]:
            size = p.stat().st_size
            if size > max_bytes:
                continue
            files.append({
                "path": str(p),
                "name": p.name,
                "size_bytes": size,
            })
        
        return {
            "success": True,
            "files": files,
            "total_found": len(all_files),
            "total_collected": len(files),
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "files": [],
        }
