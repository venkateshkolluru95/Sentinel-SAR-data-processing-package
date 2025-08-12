"""
SRTM DEM downloader for SAR processing pipeline.
"""

import os
import subprocess
import glob
import shutil
from math import floor, ceil


def download_srtm_earthdata(bounds, output_dir, earthdata_username, earthdata_password, buffer_degrees=2.0):
    """Downloads and mosaics SRTM DEM tiles with improved path handling and error recovery"""
    os.makedirs(output_dir, exist_ok=True)
    
    # Add buffer to bounds
    left, bottom, right, top = bounds
    buffered_bounds = (
        left - buffer_degrees,
        bottom - buffer_degrees,
        right + buffer_degrees,
        top + buffer_degrees
    )
    
    expanded_bounds = (
        floor(buffered_bounds[0]),
        max(-60, min(60, floor(buffered_bounds[1]))),
        ceil(buffered_bounds[2]),
        max(-60, min(60, ceil(buffered_bounds[3])))
    )
    
    print(f"Original bounds: {bounds}")
    print(f"Buffered bounds: {buffered_bounds}")
    print(f"Final expanded bounds: {expanded_bounds}")
    
    # Create temporary download directory within output_dir
    temp_download_dir = os.path.join(output_dir, 'temp_downloads')
    os.makedirs(temp_download_dir, exist_ok=True)
    
    dem_tiles = []
    failed_tiles = []
    
    # First, try to download all tiles
    for lon in range(int(expanded_bounds[0]), int(expanded_bounds[2]) + 1):
        for lat in range(int(expanded_bounds[1]), int(expanded_bounds[3]) + 1):
            hemisphere_ns = 'N' if lat >= 0 else 'S'
            hemisphere_ew = 'E' if lon >= 0 else 'W'
            tile_name = f"{hemisphere_ns}{abs(lat):02d}{hemisphere_ew}{abs(lon):03d}.SRTMGL1.hgt.zip"
            local_tile_path = os.path.join(temp_download_dir, tile_name)
            
            if not os.path.exists(local_tile_path):
                url = f"https://e4ftl01.cr.usgs.gov/MEASURES/SRTMGL1.003/2000.02.11/{tile_name}"
                
                # Use wget with full path specification
                cmd = [
                    'wget',
                    '--user', earthdata_username,
                    '--password', earthdata_password,
                    '--auth-no-challenge',
                    '--no-check-certificate',
                    '-O', local_tile_path,
                    url
                ]
                
                try:
                    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
                    print(f"Successfully downloaded: {tile_name}")
                except subprocess.CalledProcessError as e:
                    print(f"Failed to download {tile_name}: {e.stderr}")
                    # Add to failed tiles list
                    failed_tiles.append((lat, lon))
                    # If the file was created but is incomplete, remove it
                    if os.path.exists(local_tile_path):
                        os.remove(local_tile_path)
                    continue
            
            if os.path.exists(local_tile_path) and os.path.getsize(local_tile_path) > 0:
                dem_tiles.append(local_tile_path)
    
    # If we have no tiles at all, that's a fatal error
    if not dem_tiles:
        raise RuntimeError("No SRTM DEM tiles downloaded. Check credentials and connectivity.")
    
    # Log failed tiles for diagnostic purposes
    if failed_tiles:
        print(f"Failed to download {len(failed_tiles)} tiles. This is normal for ocean areas.")
        # If all tiles failed, that's suspicious and might indicate a problem
        if len(failed_tiles) == (int(expanded_bounds[2]) - int(expanded_bounds[0]) + 1) * \
                               (int(expanded_bounds[3]) - int(expanded_bounds[1]) + 1):
            print("WARNING: All tiles failed to download. Check credentials and connectivity.")
    
    # Unzip and merge DEM tiles
    unzipped_tiles = []
    for tile in dem_tiles:
        tile_base = os.path.splitext(os.path.basename(tile))[0]
        unzip_dir = os.path.join(output_dir, tile_base)
        os.makedirs(unzip_dir, exist_ok=True)
        
        try:
            subprocess.run(['unzip', '-o', tile, '-d', unzip_dir], check=True)
            hgt_files = glob.glob(os.path.join(unzip_dir, '*.hgt'))
            unzipped_tiles.extend(hgt_files)
        except subprocess.CalledProcessError as e:
            print(f"Failed to unzip {tile}: {str(e)}")
            continue
    
    # Clean up downloaded zip files
    shutil.rmtree(temp_download_dir)
    
    if not unzipped_tiles:
        raise RuntimeError("No valid DEM tiles after unzipping")
    
    # Create output filename based on bounds
    dem_filename = f"demLat_N{int(abs(expanded_bounds[3]))}_N{int(abs(expanded_bounds[1]))}_Lon_W{int(abs(expanded_bounds[0]))}_W{int(abs(expanded_bounds[2]))}.dem.wgs84"
    merged_dem = os.path.join(output_dir, dem_filename)
    
    # Merge DEM tiles with improved error handling
    try:
        merge_cmd = ['gdal_merge.py', '-o', merged_dem, '-of', 'GTiff']
        merge_cmd.extend(unzipped_tiles)
        subprocess.run(merge_cmd, check=True, capture_output=True, text=True)
        print(f"Successfully merged DEM tiles to: {merged_dem}")
    except subprocess.CalledProcessError as e:
        print(f"Failed to merge DEM tiles: {e.stderr}")
        raise
    
    return merged_dem