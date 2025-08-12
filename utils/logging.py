"""
Logging utilities for SAR processing pipeline.
"""

import os
import sys
import logging
from functools import wraps
from datetime import datetime
import io
from contextlib import redirect_stdout, redirect_stderr
import traceback


def setup_file_logging(tiff_file, logs_dir):
    """Set up a file logger for a specific TIFF file."""
    os.makedirs(logs_dir, exist_ok=True)
    
    # Create a sanitized filename for the log
    base_name = os.path.splitext(os.path.basename(tiff_file))[0]
    log_file = os.path.join(logs_dir, f"{base_name}.log")
    
    # Create a file handler
    file_handler = logging.FileHandler(log_file, mode='w')
    file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(file_formatter)
    
    # Create logger
    logger = logging.getLogger(f"sar_{base_name}")
    logger.setLevel(logging.INFO)
    
    # Clear any existing handlers
    if logger.handlers:
        for handler in logger.handlers:
            logger.removeHandler(handler)
            
    logger.addHandler(file_handler)
    
    return logger, log_file


def log_tiff_processing(tiff_file, logs_dir):
    """Decorator to log processing of a TIFF file to its own log file."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Set up logger
            logger, log_file = setup_file_logging(tiff_file, logs_dir)
            
            # Log processing start
            log_separator = "=" * 80
            logger.info(log_separator)
            logger.info(f"Starting processing of: {os.path.basename(tiff_file)}")
            logger.info(f"Timestamp: {datetime.now().isoformat()}")
            logger.info(log_separator)
            
            # Process the file and capture all output
            stdout_buffer = io.StringIO()
            stderr_buffer = io.StringIO()
            
            with open(log_file, 'a') as log_output, redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
                try:
                    result = func(*args, **kwargs)
                    
                    # Get captured output
                    stdout_content = stdout_buffer.getvalue()
                    stderr_content = stderr_buffer.getvalue()
                    
                    # Write captured output to log file
                    if stdout_content:
                        log_output.write("\n--- STDOUT CAPTURE ---\n")
                        log_output.write(stdout_content)
                    
                    if stderr_content:
                        log_output.write("\n--- STDERR CAPTURE ---\n")
                        log_output.write(stderr_content)
                    
                    # Log processing completion
                    log_output.write(f"\n{log_separator}\n")
                    log_output.write(f"Completed processing of: {os.path.basename(tiff_file)}\n")
                    log_output.write(f"Status: {result.get('status', 'unknown')}\n")
                    if 'error' in result:
                        log_output.write(f"Error: {result['error']}\n")
                    log_output.write(f"Timestamp: {datetime.now().isoformat()}\n")
                    log_output.write(f"{log_separator}\n")
                    
                    return result
                except Exception as e:
                    # Log error
                    log_output.write(f"\nERROR processing {tiff_file}: {str(e)}\n")
                    log_output.write(traceback.format_exc())
                    raise
                finally:
                    # Clean up handlers
                    for handler in logger.handlers:
                        handler.close()
                        logger.removeHandler(handler)
        
        return wrapper
    return decorator


def log_processing_event(output_base_dir, tiff_file, event_type, details):
    """
    Log processing events in a JSON file
    """
    import json
    
    log_file = os.path.join(output_base_dir, 'processing_log.json')
    
    # Read existing log or create new
    try:
        with open(log_file, 'r') as f:
            logs = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        logs = []
    
    # Add new log entry
    log_entry = {
        'timestamp': datetime.now().isoformat(),
        'file': tiff_file,
        'event_type': event_type,
        'details': details
    }
    
    logs.append(log_entry)
    
    # Write back to log file
    with open(log_file, 'w') as f:
        json.dump(logs, f, indent=2)