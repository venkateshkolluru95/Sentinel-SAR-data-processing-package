"""
Geometric utilities for SAR processing.
"""
import os
import sys

# Get the parent directory of the current file's directory
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, "..", ".."))
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

from Sentinel_SAR_processing.utils.imports import *

"""
Geometry utilities for SAR processing pipeline.
"""

import os
import tempfile
import zipfile
import xml.etree.ElementTree as ET
import asf_search as asf
import traceback


def create_wkt_from_bounds(bounds):
    """Create WKT polygon from bounding box."""
    left, bottom, right, top = bounds
    return f"POLYGON (({left} {bottom}, {left} {top}, {right} {top}, {right} {bottom}, {left} {bottom}))"


def get_sentinel_scene_extents(safe_file):
    """
    Extract the geographic bounds of a Sentinel scene from its metadata.
    
    Args:
        safe_file (str): Path to the Sentinel SAFE zip file
        
    Returns:
        tuple: (left, bottom, right, top) bounds of the scene
    """
    try:
        # Create a temporary directory to extract metadata
        with tempfile.TemporaryDirectory() as temp_dir:
            # Extract manifest.safe or manifest.xml from zip file
            with zipfile.ZipFile(safe_file, 'r') as zip_ref:
                manifest_files = [f for f in zip_ref.namelist() if 'manifest.safe' in f or 'manifest.xml' in f]
                if not manifest_files:
                    raise ValueError(f"No manifest file found in {safe_file}")
                
                manifest_file = manifest_files[0]
                zip_ref.extract(manifest_file, temp_dir)
                
                full_manifest_path = os.path.join(temp_dir, manifest_file)
                
                # Parse the manifest file
                tree = ET.parse(full_manifest_path)
                root = tree.getroot()
                
                # Find the footprint
                for elem in root.iter():
                    if 'footPrint' in elem.tag or 'footprint' in elem.tag:
                        # Extract the coordinates
                        coords_elem = elem.find('.//*coordinates') or elem.find('.//*Coordinates')
                        if coords_elem is not None:
                            coords_text = coords_elem.text.strip()
                            # Parse the coordinates
                            points = [tuple(map(float, point.split())) for point in coords_text.split()]
                            
                            # Calculate bounds
                            lons = [p[0] for p in points]
                            lats = [p[1] for p in points]
                            
                            return (min(lons), min(lats), max(lons), max(lats))
                        
                        # Alternative: look for gml:coordinates
                        ns = {'gml': 'http://www.opengis.net/gml'}
                        coords_elem = elem.find('.//gml:coordinates', ns)
                        if coords_elem is not None:
                            coords_text = coords_elem.text.strip()
                            # Parse the coordinates
                            points = [tuple(map(float, point.split(','))) for point in coords_text.split()]
                            
                            # Calculate bounds
                            lons = [p[0] for p in points]
                            lats = [p[1] for p in points]
                            
                            return (min(lons), min(lats), max(lons), max(lats))
        
        # If we couldn't extract from manifest, try using asf_search capabilities
        scene_name = os.path.basename(safe_file).replace('.zip', '')
        results = asf.granule_search([scene_name])
        
        if results and len(results) > 0:
            scene = results[0]
            wkt = scene.geometry.wkt
            
            # Parse the WKT
            if 'POLYGON' in wkt:
                coords_text = wkt.split('((')[1].split('))')[0]
                points = [tuple(map(float, point.split())) for point in coords_text.split(',')]
                
                # Calculate bounds
                lons = [p[0] for p in points]
                lats = [p[1] for p in points]
                
                return (min(lons), min(lats), max(lons), max(lats))
        
        # If all methods fail, return a conservative fallback
        print("WARNING: Could not extract precise Sentinel scene extents, using approximation")
        # Conservative estimate - Sentinel-1 scenes are roughly 250km x 250km
        buffer_degrees = 1.0  # Roughly 100km at equator
        
        # This should be passed as parameter in a real implementation
        # For now, return a global extent as fallback
        return (-180.0, -90.0, 180.0, 90.0)
        
    except Exception as e:
        print(f"Error extracting Sentinel scene extents: {e}")
        traceback.print_exc()
        
        # Return a very conservative fallback (global bounds)
        return (-180.0, -90.0, 180.0, 90.0)