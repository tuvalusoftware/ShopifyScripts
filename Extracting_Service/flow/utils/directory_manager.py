#!/usr/bin/env python3
"""Centralized directory manager service for flow processing."""
import os
from pathlib import Path
from typing import Optional
from datetime import datetime


class DirectoryManager:
    """Centralized directory manager for managing all directories used by flows.
    
    Singleton pattern: Only one instance exists throughout the application process.
    Automatically reads OUTPUT_DIR from environment variable on initialization.
    Use get_instance() to access the singleton instance.
    """
    
    _instance: Optional['DirectoryManager'] = None
    _initialized: bool = False
    
    def __new__(cls):
        """
        Create or return the singleton instance.
        """
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """
        Initialize directory manager with base output directory from environment variable.
        Reads OUTPUT_DIR from environment, defaults to "." if not set.
        """
        # Only initialize once
        if not DirectoryManager._initialized:
            # Read OUTPUT_DIR from environment variable
            output_dir = os.getenv("OUTPUT_DIR", ".")
            output_dir = os.path.abspath(output_dir)
            
            # If output_dir is /app or /app/* and not writable (running locally), use local directory
            if output_dir.startswith("/app"):
                test_path = Path(output_dir)
                try:
                    test_path.mkdir(parents=True, exist_ok=True)
                    test_file = test_path / ".test_write_check"
                    test_file.touch()
                    test_file.unlink()
                except (OSError, PermissionError):
                    output_dir = os.path.abspath("./data")
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.warning(f"Cannot write to /app, using local directory: {output_dir}")
            
            self._base_output_dir = Path(output_dir).expanduser().resolve()
            self._ensure_dir(self._base_output_dir)
            
            # Flow1 specific directories (lazy initialization)
            self._attachments_dir: Optional[Path] = None
            self._temp_download_dir: Optional[Path] = None
            self._extraction_out_dir: Optional[Path] = None
            
            # Flow2 specific directories (lazy initialization)
            self._run_dir: Optional[Path] = None
            self._responses_dir: Optional[Path] = None
            
            DirectoryManager._initialized = True
    
    @classmethod
    def get_instance(cls) -> 'DirectoryManager':
        """
        Get the singleton instance. Automatically initializes if not already initialized.
        
        Returns:
            DirectoryManager: The singleton instance
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def initialize(cls) -> 'DirectoryManager':
        """
        Initialize the singleton instance (reads OUTPUT_DIR from environment).
        
        Returns:
            DirectoryManager: The singleton instance
        """
        return cls()
    
    @classmethod
    def is_initialized(cls) -> bool:
        """
        Check if the singleton instance has been initialized.
        
        Returns:
            bool: True if initialized, False otherwise
        """
        return cls._initialized and cls._instance is not None
    
    
    def _ensure_dir(self, path: Path) -> Path:
        """Ensure directory exists and return Path object."""
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    # Base directory accessors
    @property
    def base_output_dir(self) -> str:
        """Get base output directory path as string."""
        return str(self._base_output_dir)
    
    @property
    def base_output_path(self) -> Path:
        """Get base output directory as Path object."""
        return self._base_output_dir
    
    # Flow1 directory accessors
    def get_attachments_dir(self) -> str:
        """Get attachments directory path (Flow1)."""
        if self._attachments_dir is None:
            self._attachments_dir = self._base_output_dir / "attachments_from_eml"
            self._ensure_dir(self._attachments_dir)
        return str(self._attachments_dir)
    
    def get_temp_download_dir(self, temp_dir_name: str = "temp_eml_downloads") -> str:
        """Get temporary download directory path (Flow1)."""
        if self._temp_download_dir is None:
            self._temp_download_dir = self._base_output_dir / temp_dir_name
            self._ensure_dir(self._temp_download_dir)
        return str(self._temp_download_dir)
    
    def get_extraction_out_dir(self, subdir: Optional[str] = None) -> str:
        """Get extraction output directory path (Flow1)."""
        if self._extraction_out_dir is None:
            if subdir:
                self._extraction_out_dir = self._base_output_dir / subdir
            else:
                self._extraction_out_dir = self._base_output_dir / "extraction_outputs"
            self._ensure_dir(self._extraction_out_dir)
        return str(self._extraction_out_dir)
    
    def get_extraction_log_dir(self) -> str:
        """Get extraction log directory path (Flow1)."""
        extraction_dir = self.get_extraction_out_dir()
        log_dir = Path(extraction_dir) / "logs"
        self._ensure_dir(log_dir)
        return str(log_dir)
    
    # Flow2 directory accessors
    def setup_flow2_directories(self, make_run_subdir: bool = True) -> None:
        """
        Setup Flow2 specific directories (run_dir and responses_dir).
        
        Args:
            make_run_subdir: Whether to create run subdirectory
        """
        if make_run_subdir:
            run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
            self._run_dir = self._base_output_dir / f"run_{run_id}"
        else:
            self._run_dir = self._base_output_dir
        
        self._ensure_dir(self._run_dir)
        self._responses_dir = self._run_dir / "responses"
        self._ensure_dir(self._responses_dir)
    
    def get_run_dir(self) -> str:
        """Get run directory path (Flow2)."""
        if self._run_dir is None:
            self.setup_flow2_directories()
        return str(self._run_dir)
    
    def get_responses_dir(self) -> str:
        """Get responses directory path (Flow2)."""
        if self._responses_dir is None:
            self.setup_flow2_directories()
        return str(self._responses_dir)
    
    # Utility methods
    def join(self, *parts: str) -> str:
        """Join path parts relative to base output directory."""
        return str(self._base_output_dir.joinpath(*parts))
    
    def ensure_subdir(self, subdir: str) -> str:
        """Ensure a subdirectory exists under base output directory."""
        subdir_path = self._base_output_dir / subdir
        self._ensure_dir(subdir_path)
        return str(subdir_path)
    
    def get_path(self, *parts: str) -> str:
        """Get a path relative to base output directory."""
        return str(self._base_output_dir.joinpath(*parts))
    
    def exists(self, *parts: str) -> bool:
        """Check if a path exists relative to base output directory."""
        return self._base_output_dir.joinpath(*parts).exists()
    
    def is_writable(self) -> bool:
        """Check if base output directory is writable."""
        try:
            test_file = self._base_output_dir / ".test_write_check"
            test_file.touch()
            test_file.unlink()
            return True
        except (OSError, PermissionError):
            return False
    
    def reset_flow2_directories(self) -> None:
        """Reset Flow2 directories (useful for testing or re-initialization)."""
        self._run_dir = None
        self._responses_dir = None
    
    def reset_flow1_directories(self) -> None:
        """Reset Flow1 directories (useful for testing or re-initialization)."""
        self._attachments_dir = None
        self._temp_download_dir = None
        self._extraction_out_dir = None
    
    @classmethod
    def reset_instance(cls) -> None:
        """
        Reset the singleton instance (useful for testing).
        This clears the singleton state and allows re-initialization.
        """
        cls._instance = None
        cls._initialized = False