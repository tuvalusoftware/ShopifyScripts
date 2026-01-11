#!/usr/bin/env python3
"""Centralized logging configuration for flow modules."""
import logging
import os
import sys
from typing import Optional


def setup_logger(
    name: str,
    level: Optional[str] = None,
    format_string: Optional[str] = None,
    stream: Optional[sys.stdout] = None,
) -> logging.Logger:
    """
    Setup and configure a logger instance.
    
    Args:
        name: Logger name (typically __name__)
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL). 
               Defaults to INFO, or LOG_LEVEL env var if set.
        format_string: Custom format string. Defaults to standard format.
        stream: Output stream (defaults to stderr for consistency with eprint)
        
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    
    # Avoid duplicate handlers if logger already configured
    if logger.handlers:
        return logger
    
    # Set log level
    if level is None:
        level = os.getenv("LOG_LEVEL", "INFO").upper()
    
    log_level = getattr(logging, level, logging.INFO)
    logger.setLevel(log_level)
    
    # Default format: timestamp, level, name, message
    if format_string is None:
        format_string = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    
    formatter = logging.Formatter(format_string, datefmt="%Y-%m-%d %H:%M:%S")
    
    # Use stderr by default (consistent with eprint behavior)
    if stream is None:
        stream = sys.stderr
    
    handler = logging.StreamHandler(stream)
    handler.setLevel(log_level)
    handler.setFormatter(formatter)
    
    logger.addHandler(handler)
    
    # Prevent propagation to root logger to avoid duplicate messages
    logger.propagate = False
    
    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Get or create a logger instance with default configuration.
    
    Convenience function that calls setup_logger with defaults.
    
    Args:
        name: Logger name (typically __name__)
        
    Returns:
        Configured logger instance
    """
    return setup_logger(name)
