"""
Registry management utilities for SAR processing pipeline.
"""

import os
import json
import time
import shutil
import tempfile
import traceback
import glob
import rasterio
from datetime import datetime


def fix_load_sar_registry(output_base_dir):
    """
    Modified load SAR registry function that avoids file locking issues and improves caching
    """
    registry_file = os.path.join(output_base_dir, 'sar_registry.json')
    print(f"Loading SAR registry from: {registry_file}")
    
    # Create registry file if it doesn't exist
    if not os.path.exists(registry_file):
        print("Registry file does not exist, creating new registry")
        try:
            os.makedirs(os.path.dirname(registry_file), exist_ok=True)
            with open(registry_file, 'w') as f:
                f.write('{}')
            return {}
        except Exception as e:
            print(f"Error creating registry file: {e}")
            return {}
    
    # Read the registry file without locking
    try:
        with open(registry_file, 'r') as f:
            try:
                registry = json.load(f)
                print(f"Successfully loaded registry with {len(registry)} entries")
                return registry
            except json.JSONDecodeError as e:
                print(f"Error decoding registry JSON: {e}")
                print("Creating backup of corrupted registry and starting fresh")
                # Create backup of corrupted file
                backup_file = f"{registry_file}.bak.{int(time.time())}"
                shutil.copy2(registry_file, backup_file)
                return {}
    except Exception as e:
        print(f"Error loading registry: {e}")
        traceback.print_exc()
        return {}


def fix_save_sar_registry(output_base_dir, registry):
    """
    Modified save SAR registry function that uses atomic write operations
    but avoids file locking issues
    """
    registry_file = os.path.join(output_base_dir, 'sar_registry.json')
    
    # Create a temporary file for atomic write
    try:
        temp_file = tempfile.NamedTemporaryFile(mode='w', delete=False, dir=os.path.dirname(registry_file))
        # Write to temp file
        json.dump(registry, temp_file, indent=2)
        temp_file.flush()
        os.fsync(temp_file.fileno())  # Ensure data is written to disk
        temp_file.close()
        
        # Now safely move the temp file to the target location (atomic operation)
        os.rename(temp_file.name, registry_file)
        print(f"Successfully saved registry with {len(registry)} entries")
        return True
    except Exception as e:
        print(f"Error saving registry: {e}")
        traceback.print_exc()
        # Clean up the temp file if it exists
        if 'temp_file' in locals() and os.path.exists(temp_file.name):
            os.unlink(temp_file.name)
        return False


def check_scene_overlap(maxar_bounds, registry, disaster_phase, maxar_date, tolerance=0.01, date_tolerance_days=30):
    """
    Check if MAXAR bounds fall within any previously processed Sentinel scene with matching disaster phase.
    Returns scene_id and processed_files if a match is found.
    
    Args:
        maxar_bounds (tuple): (left, bottom, right, top) bounds of MAXAR tiff
        registry (dict): SAR scene registry
        disaster_phase (str): 'pre_disaster' or 'post_disaster'
        maxar_date (datetime): Date of the MAXAR image
        tolerance (float): Tolerance for MAXAR chip overlap check
        date_tolerance_days (int): Maximum allowed date difference in days
    
    Returns:
        tuple: (scene_id, processed_files) if found, else (None, None)
    """
    # If disaster phase is unknown, use a more conservative search strategy
    strict_phase_check = disaster_phase != 'unknown'
    if not maxar_bounds or len(maxar_bounds) != 4:
        raise ValueError(f"Invalid MAXAR bounds provided: {maxar_bounds}")
        
    if not registry:
        print("Empty registry, no overlap check needed")
        return None, None
        
    print(f"\n--- Sentinel Scene Coverage Check ({disaster_phase}) ---")
    maxar_left, maxar_bottom, maxar_right, maxar_top = maxar_bounds
    print(f"Current MAXAR chip bounds: {maxar_bounds}")
    print(f"MAXAR date: {maxar_date.isoformat()}")
    
    # First check if these exact MAXAR bounds have been processed before
    for scene_id, info in registry.items():
        # Skip if disaster phase doesn't match (only if strict check is enabled)
        scene_disaster_phase = info.get('disaster_phase')
        if strict_phase_check and scene_disaster_phase and scene_disaster_phase != disaster_phase:
            print(f"Skipping scene {scene_id} - disaster phase mismatch: {scene_disaster_phase} != {disaster_phase}")
            continue
            
        if 'maxar_chips' in info:
            for chip_id, chip_info in info['maxar_chips'].items():
                chip_bounds = chip_info.get('bounds')
                if not chip_bounds or len(chip_bounds) != 4:
                    continue
                
                # Calculate coordinate differences for exact MAXAR chip match
                diff_left = abs(maxar_bounds[0] - chip_bounds[0])
                diff_bottom = abs(maxar_bounds[1] - chip_bounds[1])
                diff_right = abs(maxar_bounds[2] - chip_bounds[2])
                diff_top = abs(maxar_bounds[3] - chip_bounds[3])
                
                # Check if all differences are within tolerance (exact MAXAR chip match)
                if (diff_left <= tolerance and 
                    diff_bottom <= tolerance and 
                    diff_right <= tolerance and 
                    diff_top <= tolerance):
                    
                    print(f"Found exact matching MAXAR chip in scene {scene_id}")
                    return scene_id, chip_info.get('processed_files', {})
    
    # If no exact MAXAR match, check if it falls within any Sentinel scene extent with matching disaster phase
    for scene_id, info in registry.items():
        # Skip if disaster phase doesn't match (only if strict check is enabled)
        scene_disaster_phase = info.get('disaster_phase')
        if strict_phase_check and scene_disaster_phase and scene_disaster_phase != disaster_phase:
            print(f"Skipping scene {scene_id} - disaster phase mismatch: {scene_disaster_phase} != {disaster_phase}")
            continue
            
        # For non-strict phase check, log the potential mismatch but continue
        if not strict_phase_check and scene_disaster_phase and scene_disaster_phase != disaster_phase:
            print(f"WARNING: Potential disaster phase mismatch with scene {scene_id} ({scene_disaster_phase} vs {disaster_phase})")
            print("         Continuing anyway since disaster phase is uncertain")
            
        # Check date proximity
        scene_date = None
        if 'acquisition_date' in info:
            try:
                scene_date = datetime.fromisoformat(info['acquisition_date'].replace('Z', '+00:00'))
                date_diff = abs((scene_date - maxar_date).days)
                
                if date_diff > date_tolerance_days:
                    print(f"Skipping scene {scene_id} - date too different: {date_diff} days")
                    continue
                    
                print(f"Scene date: {scene_date.isoformat()}, difference: {date_diff} days")
            except Exception as e:
                print(f"Error parsing scene date: {e}")
        
        sentinel_bounds = info.get('sentinel_bounds')
        if not sentinel_bounds or len(sentinel_bounds) != 4:
            print(f"No valid Sentinel bounds for scene {scene_id}, skipping")
            continue
        
        print(f"Checking if MAXAR bounds {maxar_bounds} are within Sentinel bounds {sentinel_bounds}")
        
        # Correctly interpret Sentinel bounds as [min_lat, min_lon, max_lat, max_lon]
        s_min_lat, s_min_lon, s_max_lat, s_max_lon = sentinel_bounds
        
        # Check if MAXAR bounds are within Sentinel scene bounds (with larger buffer)
        buffer = 0.1  # Larger buffer to account for estimation errors
        is_contained = (
            maxar_left >= s_min_lon - buffer and 
            maxar_right <= s_max_lon + buffer and 
            maxar_bottom >= s_min_lat - buffer and 
            maxar_top <= s_max_lat + buffer
        )
        
        if is_contained:
            print(f"MAXAR chip falls within Sentinel scene: {scene_id}")
            print(f"Sentinel bounds: {sentinel_bounds}")
            
            # Verify processed VV/VH files exist and are valid
            processed_files = info.get('processed_files', {})
            try:
                print("\nValidating processed files...")
                for file_type, file_path in processed_files.items():
                    if file_type not in ['vv', 'vh']:
                        continue
                        
                    print(f"Checking {file_type}: {file_path}")
                    
                    # Check file exists
                    if not os.path.exists(file_path):
                        print(f"File does not exist: {file_path}")
                        break
                    
                    # Check file size
                    file_size = os.path.getsize(file_path)
                    print(f"File size: {file_size} bytes")
                    if file_size == 0:
                        print(f"Empty file: {file_path}")
                        break
                    
                    # Additional validation for raster files
                    try:
                        with rasterio.open(file_path) as src:
                            if src.count == 0 or src.width == 0 or src.height == 0:
                                print(f"Invalid raster dimensions for {file_path}")
                                break
                    except Exception as e:
                        print(f"Error opening raster {file_path}: {e}")
                        break
                else:
                    print("All files validated successfully!")
                    return scene_id, processed_files
                    
            except Exception as e:
                print(f"Error validating files: {e}")
        else:
            print(f"MAXAR chip does NOT fall within Sentinel scene {scene_id}")
    
    print("No matching scene found.")
    return None, None


def register_processed_scene(registry, scene_id, sentinel_bounds, maxar_bounds, processed_files, 
                         maxar_id=None, disaster_phase=None, acquisition_date=None):
    """
    Register processed scene with improved error handling
    """
    try:
        # Round bounds to a consistent number of decimal places
        rounded_sentinel_bounds = [
            round(sentinel_bounds[0], 6),
            round(sentinel_bounds[1], 6),
            round(sentinel_bounds[2], 6),
            round(sentinel_bounds[3], 6)
        ]
        
        rounded_maxar_bounds = [
            round(maxar_bounds[0], 6),
            round(maxar_bounds[1], 6),
            round(maxar_bounds[2], 6),
            round(maxar_bounds[3], 6)
        ]
        
        # Generate a default MAXAR ID if not provided
        if not maxar_id:
            maxar_id = f"maxar_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        # Store acquisition date as ISO string if provided
        acquisition_date_str = None
        if acquisition_date:
            acquisition_date_str = acquisition_date.isoformat()
        
        # Make a deep copy of the registry to avoid reference issues
        registry_copy = {}
        for key, value in registry.items():
            registry_copy[key] = value.copy() if isinstance(value, dict) else value
        
        # If scene exists, update it, otherwise create new entry
        if scene_id in registry_copy:
            if 'maxar_chips' not in registry_copy[scene_id]:
                registry_copy[scene_id]['maxar_chips'] = {}
            
            # Update existing entry with disaster phase if not already set
            if disaster_phase and 'disaster_phase' not in registry_copy[scene_id]:
                registry_copy[scene_id]['disaster_phase'] = disaster_phase
                
            # Update acquisition date if not already set
            if acquisition_date_str and 'acquisition_date' not in registry_copy[scene_id]:
                registry_copy[scene_id]['acquisition_date'] = acquisition_date_str
            
            registry_copy[scene_id]['maxar_chips'][maxar_id] = {
                'bounds': rounded_maxar_bounds,
                'processed_files': processed_files,
                'processing_date': datetime.now().isoformat(),
                'disaster_phase': disaster_phase
            }
        else:
            # Create new scene entry with both Sentinel and MAXAR information
            registry_copy[scene_id] = {
                'sentinel_bounds': rounded_sentinel_bounds,
                'processed_files': processed_files,
                'processing_date': datetime.now().isoformat(),
                'disaster_phase': disaster_phase,
                'acquisition_date': acquisition_date_str,
                'maxar_chips': {
                    maxar_id: {
                        'bounds': rounded_maxar_bounds,
                        'processed_files': processed_files,
                        'processing_date': datetime.now().isoformat(),
                        'disaster_phase': disaster_phase
                    }
                }
            }
        
        return registry_copy
    except Exception as e:
        print(f"Error registering processed scene: {e}")
        traceback.print_exc()
        # Return original registry unchanged if there was an error
        return registry


def update_registry_atomic_fixed(output_base_dir, scene_id, sentinel_bounds, maxar_bounds, processed_files, 
                        maxar_id=None, disaster_phase=None, acquisition_date=None, max_retries=3):
    """
    Atomic registry update with retries and improved file handling
    """
    for attempt in range(max_retries):
        try:
            # Load current registry with fixed function
            registry = fix_load_sar_registry(output_base_dir)
            
            # Make a deep copy of the registry
            registry_copy = {}
            for key, value in registry.items():
                registry_copy[key] = value.copy() if isinstance(value, dict) else value
            
            # Convert acquisition_date to string if it's a datetime object
            acquisition_date_str = None
            if acquisition_date:
                if isinstance(acquisition_date, datetime):
                    acquisition_date_str = acquisition_date.isoformat()
                else:
                    acquisition_date_str = acquisition_date
            
            # Current timestamp as string
            current_time_str = datetime.now().isoformat()
            
            # If scene exists, update it, otherwise create new entry
            if scene_id in registry_copy:
                if 'maxar_chips' not in registry_copy[scene_id]:
                    registry_copy[scene_id]['maxar_chips'] = {}
                
                # Update existing entry with disaster phase if not already set
                if disaster_phase and 'disaster_phase' not in registry_copy[scene_id]:
                    registry_copy[scene_id]['disaster_phase'] = disaster_phase
                    
                # Update acquisition date if not already set
                if acquisition_date_str and 'acquisition_date' not in registry_copy[scene_id]:
                    registry_copy[scene_id]['acquisition_date'] = acquisition_date_str
                
                registry_copy[scene_id]['maxar_chips'][maxar_id] = {
                    'bounds': maxar_bounds,
                    'processed_files': processed_files,
                    'processing_date': current_time_str,
                    'disaster_phase': disaster_phase
                }
            else:
                # Create new scene entry with both Sentinel and MAXAR information
                registry_copy[scene_id] = {
                    'sentinel_bounds': sentinel_bounds,
                    'processed_files': processed_files,
                    'processing_date': current_time_str,
                    'disaster_phase': disaster_phase,
                    'acquisition_date': acquisition_date_str,
                    'maxar_chips': {
                        maxar_id: {
                            'bounds': maxar_bounds,
                            'processed_files': processed_files,
                            'processing_date': current_time_str,
                            'disaster_phase': disaster_phase
                        }
                    }
                }
            
            # Save updated registry with fixed function
            if fix_save_sar_registry(output_base_dir, registry_copy):
                # Verify update was successful
                verification_registry = fix_load_sar_registry(output_base_dir)
                if scene_id in verification_registry:
                    print(f"Successfully verified registry update for scene {scene_id}")
                    return True
                else:
                    print(f"Failed to verify registry update for scene {scene_id}, retrying...")
            else:
                print(f"Failed to save registry, retrying...")
        except Exception as e:
            print(f"Error during registry update (attempt {attempt+1}/{max_retries}): {e}")
            traceback.print_exc()
            time.sleep(1)  # Brief pause before retry
    
    print(f"Failed to update registry after {max_retries} attempts")
    return False


def validate_sar_registry(output_base_dir):
    """
    Validate that all processed files are correctly registered
    """
    registry_file = os.path.join(output_base_dir, 'sar_registry.json')
    final_dir = os.path.join(output_base_dir, 'final')
    
    # Get all final processed files
    processed_files = glob.glob(os.path.join(final_dir, '*_RTC_clipped.tif'))
    
    # Load current registry
    registry = fix_load_sar_registry(output_base_dir)
    
    # Check if all files are registered
    missing_files = []
    for file_path in processed_files:
        file_name = os.path.basename(file_path)
        found = False
        
        # Check if this file is registered under any scene
        for scene_id, scene_info in registry.items():
            for chip_id, chip_info in scene_info.get('maxar_chips', {}).items():
                if 'processed_files' in chip_info and 'clipped' in chip_info['processed_files']:
                    if os.path.basename(chip_info['processed_files']['clipped']) == file_name:
                        found = True
                        break
            
            if found:
                break
        
        if not found:
            missing_files.append(file_path)
    
    # Report results
    if missing_files:
        print(f"Found {len(missing_files)} files missing from registry:")
        for file in missing_files[:10]:  # Show first 10 for brevity
            print(f"  - {os.path.basename(file)}")
        if len(missing_files) > 10:
            print(f"  ... and {len(missing_files) - 10} more")
        return False
    else:
        print(f"All {len(processed_files)} processed files are correctly registered")
        return True


def rebuild_sar_registry(output_base_dir):
    """
    Rebuild SAR registry from existing processed files
    """
    # Directories
    dirs = {
        'final': os.path.join(output_base_dir, 'final'),
        'rtc': os.path.join(output_base_dir, 'rtc'),
        'dem': os.path.join(output_base_dir, 'dem'),
        'orbit': os.path.join(output_base_dir, 'orbit'),
        'raw': os.path.join(output_base_dir, 'raw')
    }
    
    # Create backup of existing registry
    registry_file = os.path.join(output_base_dir, 'sar_registry.json')
    if os.path.exists(registry_file):
        backup_file = f"{registry_file}.backup.{int(time.time())}"
        shutil.copy2(registry_file, backup_file)
        print(f"Created backup of existing registry at {backup_file}")
    
    # Initialize new registry
    new_registry = {}
    
    # Get all final processed files
    final_files = glob.glob(os.path.join(dirs['final'], '*_RTC_clipped.tif'))
    print(f"Found {len(final_files)} processed files to register")
    
    # Process each file
    for final_file in final_files:
        try:
            base_name = os.path.splitext(os.path.basename(final_file))[0].replace('_RTC_clipped', '')
            print(f"\nProcessing {base_name}")
            
            # Determine disaster phase
            disaster_phase = None
            if 'pre_disaster' in base_name:
                disaster_phase = 'pre_disaster'
            elif 'post_disaster' in base_name:
                disaster_phase = 'post_disaster'
            
            # Find corresponding RTC files (VV and VH)
            rtc_dir_candidates = glob.glob(os.path.join(dirs['rtc'], base_name))
            if not rtc_dir_candidates:
                print(f"No RTC directory found for {base_name}, skipping")
                continue
                
            rtc_dir = rtc_dir_candidates[0]
            vv_files = glob.glob(os.path.join(rtc_dir, '*VV*.tif'))
            vh_files = glob.glob(os.path.join(rtc_dir, '*VH*.tif'))
            
            if not vv_files or not vh_files:
                print(f"Missing VV or VH files for {base_name}, skipping")
                continue
                
            # Find Sentinel scene ID from directory contents
            safe_files = []
            for root, dirs, files in os.walk(os.path.join(output_base_dir, 'raw')):
                for file in files:
                    if file.endswith('.zip') and 'S1' in file and 'SLC' in file:
                        safe_files.append(os.path.join(root, file))
            
            # Extract Sentinel ID from filename
            scene_id = None
            for safe_file in safe_files:
                safe_basename = os.path.basename(safe_file)
                if safe_basename.startswith('S1') and safe_basename.endswith('.zip'):
                    scene_id = safe_basename.replace('.zip', '')
                    break
            
            if not scene_id:
                print(f"Could not determine Sentinel ID for {base_name}, skipping")
                continue
            
            # Get bounds from final file
            maxar_bounds = None
            with rasterio.open(final_file) as src:
                bounds = src.bounds
                maxar_bounds = (bounds.left, bounds.bottom, bounds.right, bounds.top)
            
            if not maxar_bounds:
                print(f"Could not determine bounds for {base_name}, skipping")
                continue
                
            # Use approximate Sentinel bounds if actual ones not available
            # (conservative estimate covering a large area)
            sentinel_bounds = [
                maxar_bounds[0] - 1.0,  # left with buffer
                maxar_bounds[1] - 1.0,  # bottom with buffer
                maxar_bounds[2] + 1.0,  # right with buffer
                maxar_bounds[3] + 1.0   # top with buffer
            ]
            
            # Collect processed files
            processed_files = {
                'vv': vv_files[0],
                'vh': vh_files[0],
                'clipped': final_file
            }
            
            # Add to registry
            if scene_id not in new_registry:
                new_registry[scene_id] = {
                    'sentinel_bounds': sentinel_bounds,
                    'processed_files': {
                        'vv': vv_files[0],
                        'vh': vh_files[0]
                    },
                    'processing_date': datetime.now().isoformat(),
                    'disaster_phase': disaster_phase,
                    'acquisition_date': None,  # Not available during rebuild
                    'maxar_chips': {}
                }
            
            # Add MAXAR chip
            new_registry[scene_id]['maxar_chips'][base_name] = {
                'bounds': maxar_bounds,
                'processed_files': processed_files,
                'processing_date': datetime.now().isoformat(),
                'disaster_phase': disaster_phase
            }
            
            print(f"Added {base_name} to registry under scene {scene_id}")
            
        except Exception as e:
            print(f"Error processing {final_file}: {e}")
            traceback.print_exc()
    
    # Save new registry
    fix_save_sar_registry(output_base_dir, new_registry)
    print(f"\nRebuilt registry with {len(new_registry)} scene entries")
    
    return new_registry