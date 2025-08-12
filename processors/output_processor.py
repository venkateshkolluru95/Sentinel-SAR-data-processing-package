"""
Output processing utilities for RTC data.
"""

import os
import rasterio
from osgeo import gdal


def clip_and_merge_rtc_output(vv_file, vh_file, reference_tiff, output_file):
    """
    Clip RTC output to match reference MAXAR tiff and merge bands with 10m resolution.
    
    Args:
        vv_file: Path to VV polarization file (UTM)
        vh_file: Path to VH polarization file (UTM)
        reference_tiff: Path to reference MAXAR tiff (WGS84)
        output_file: Path to save output file
    """
    # Print debug information for input files
    print("\n=== Input File Information ===")
    for file_path, desc in [(vv_file, "VV"), (vh_file, "VH"), (reference_tiff, "Reference MAXAR")]:
        try:
            with rasterio.open(file_path) as src:
                print(f"\n{desc} File: {file_path}")
                print(f"CRS: {src.crs}")
                print(f"Transform: {src.transform}")
                print(f"Resolution: {src.res}")
                print(f"Bounds: {src.bounds}")
                print(f"Size: {src.width}x{src.height}")
                print(f"Dtype: {src.dtypes[0]}")
        except Exception as e:
            print(f"Error reading {desc} file: {e}")

    # Open reference file to get target extent
    with rasterio.open(reference_tiff) as ref:
        target_bounds = ref.bounds
        target_crs = ref.crs
    
    print("\n=== Processing Steps ===")
    
    # Process VV band
    print(f"\nProcessing VV band:")
    print(f"Source: {vv_file}")
    print(f"Target bounds: {target_bounds}")
    vv_warped = gdal.Warp('',
        vv_file,
        format='MEM',
        dstSRS='EPSG:4326',  # WGS84
        outputBounds=[target_bounds.left, target_bounds.bottom, 
                     target_bounds.right, target_bounds.top],
        xRes=0.0001,  # Approximately 10m at equator
        yRes=0.0001,
        resampleAlg=gdal.GRA_Bilinear,
        outputType=gdal.GDT_Float32
    )
    
    if vv_warped is None:
        raise RuntimeError("Failed to warp VV band")
    
    print(f"VV warped dimensions: {vv_warped.RasterXSize} x {vv_warped.RasterYSize}")
    print(f"VV geotransform: {vv_warped.GetGeoTransform()}")
    
    # Process VH band
    print(f"\nProcessing VH band:")
    print(f"Source: {vh_file}")
    vh_warped = gdal.Warp('',
        vh_file,
        format='MEM',
        dstSRS='EPSG:4326',  # WGS84
        outputBounds=[target_bounds.left, target_bounds.bottom, 
                     target_bounds.right, target_bounds.top],
        xRes=0.0001,  # Approximately 10m at equator
        yRes=0.0001,
        resampleAlg=gdal.GRA_Bilinear,
        outputType=gdal.GDT_Float32
    )
    
    if vh_warped is None:
        raise RuntimeError("Failed to warp VH band")
    
    print(f"VH warped dimensions: {vh_warped.RasterXSize} x {vh_warped.RasterYSize}")
    print(f"VH geotransform: {vh_warped.GetGeoTransform()}")
    
    # Verify dimensions match
    if (vv_warped.RasterXSize != vh_warped.RasterXSize or 
        vv_warped.RasterYSize != vh_warped.RasterYSize):
        raise RuntimeError(f"Band dimensions don't match: VV={vv_warped.RasterXSize}x{vv_warped.RasterYSize}, "
                         f"VH={vh_warped.RasterXSize}x{vh_warped.RasterYSize}")
    
    # Create output dataset
    print(f"\nCreating output file: {output_file}")
    driver = gdal.GetDriverByName('GTiff')
    out_ds = driver.Create(
        output_file,
        vv_warped.RasterXSize,
        vv_warped.RasterYSize,
        2,  # Two bands (VV and VH)
        gdal.GDT_Float32,
        options=['COMPRESS=LZW', 'TILED=YES', 'BIGTIFF=YES']
    )
    
    if out_ds is None:
        raise RuntimeError("Failed to create output dataset")
    
    # Set spatial reference and geotransform
    out_ds.SetProjection(vv_warped.GetProjection())
    out_ds.SetGeoTransform(vv_warped.GetGeoTransform())
    
    # Read and write data
    print("\nReading and writing band data...")
    vv_data = vv_warped.ReadAsArray()
    vh_data = vh_warped.ReadAsArray()
    
    if vv_data is None or vh_data is None:
        raise RuntimeError("Failed to read warped data")
    
    print(f"VV data shape: {vv_data.shape}")
    print(f"VH data shape: {vh_data.shape}")
    
    # Write bands
    out_ds.GetRasterBand(1).WriteArray(vv_data)
    out_ds.GetRasterBand(2).WriteArray(vh_data)
    
    # Set band descriptions
    out_ds.GetRasterBand(1).SetDescription('VV')
    out_ds.GetRasterBand(2).SetDescription('VH')
    
    # Clean up
    out_ds = None
    vv_warped = None
    vh_warped = None
    
    # Verify output file
    print("\n=== Output File Information ===")
    try:
        with rasterio.open(output_file) as src:
            print(f"Output file: {output_file}")
            print(f"CRS: {src.crs}")
            print(f"Transform: {src.transform}")
            print(f"Resolution: {src.res}")
            print(f"Bounds: {src.bounds}")
            print(f"Size: {src.width}x{src.height}")
            print(f"Band count: {src.count}")
            print(f"Dtypes: {src.dtypes}")
    except Exception as e:
        print(f"Error reading output file: {e}")
    
    print("\nProcessing completed successfully")
    return output_file


def validate_processed_files(processed_files):
    """
    Comprehensive validation of processed files with detailed logging
    """
    try:
        for file_type, file_path in processed_files.items():
            print(f"\nValidating {file_type} file: {file_path}")
            
            # Check file exists
            if not os.path.exists(file_path):
                print(f"ERROR: Missing {file_type} file: {file_path}")
                return False
            
            # Check file size
            file_size = os.path.getsize(file_path)
            print(f"File size: {file_size} bytes")
            if file_size == 0:
                print(f"ERROR: Empty {file_type} file: {file_path}")
                return False
            
            # Validate raster files
            if file_type in ['vv', 'vh']:
                try:
                    with rasterio.open(file_path) as src:
                        print(f"Raster info:")
                        print(f"  Bands: {src.count}")
                        print(f"  Width: {src.width}")
                        print(f"  Height: {src.height}")
                        print(f"  CRS: {src.crs}")
                        
                        # Check if raster is readable and has data
                        if src.count == 0 or src.width == 0 or src.height == 0:
                            print(f"ERROR: Invalid raster file: {file_type}")
                            return False
                except Exception as e:
                    print(f"ERROR validating {file_type} raster file: {e}")
                    return False
        
        print("All files validated successfully.")
        return True
    except Exception as e:
        print(f"ERROR in file validation: {e}")
        return False