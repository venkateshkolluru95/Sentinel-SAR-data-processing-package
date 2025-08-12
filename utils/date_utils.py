"""
Date handling utilities for SAR processing.
"""
from datetime import datetime
import re
import os
import sys

# Get the parent directory of the current file's directory
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, "..", ".."))
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

from Sentinel_SAR_processing.utils.imports import *


"""
Date parsing utilities for SAR processing pipeline.
"""

import re
from datetime import datetime


def parse_date(date_str):
    """Parse ISO format date strings with Z timezone and milliseconds."""
    try:
        if date_str.endswith('Z'):
            return datetime.strptime(date_str.replace('Z', '+0000').replace('.000', ''), "%Y-%m-%dT%H:%M:%S%z")
        if '+0000' in date_str:
            return datetime.strptime(date_str.replace('.000', ''), "%Y-%m-%dT%H:%M:%S%z")
        return datetime.fromisoformat(date_str)
    except ValueError as e:
        print(f"Error parsing date {date_str}: {str(e)}")
        raise


def extract_scene_date(scene_name):
    """
    Extract the acquisition date from Sentinel-1 scene name with better error handling.
    """
    if not scene_name:
        raise ValueError("Empty scene name provided")
        
    date_pattern = r'\d{8}T\d{6}'
    match = re.search(date_pattern, scene_name)
    if not match:
        raise ValueError(f"Could not extract date from scene name: {scene_name}")
    
    try:
        date_str = match.group(0)
        return datetime.strptime(date_str, "%Y%m%dT%H%M%S")
    except ValueError as e:
        raise ValueError(f"Invalid date format in scene name {scene_name}: {str(e)}")