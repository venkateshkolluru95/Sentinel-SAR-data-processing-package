#!/usr/bin/env python3
"""
Main entry point for SAR disaster processing pipeline.
"""

import argparse
import sys
import os
import logging
from datetime import datetime

# Add the current directory to Python path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.settings import load_config, create_default_config_file, ProcessingConfig
from utils.registry import validate_sar_registry, rebuild_sar_registry
from utils.logging import log_processing_event


def setup_logging(config: ProcessingConfig):
    """Setup logging configuration"""
    log_level = getattr(logging, config.log_level.upper())
    
    # Create logs directory
    logs_dir = os.path.join(config.output_dir, 'logs')
    os.makedirs(logs_dir, exist_ok=True)
    
    # Setup basic logger
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(os.path.join(logs_dir, 'main.log')),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    return logging.getLogger(__name__)


def process_scenes(config: ProcessingConfig):
    """Main processing function with improved logging"""
    from processors.rtc_config import generate_rtc_runconfig, create_slurm_job_script, run_rtc_processing
    from processors.output_processor import clip_and_merge_rtc_output, validate_processed_files
    from downloaders.bulk_downloader import bulk_downloader
    from downloaders.dem_downloader import download_srtm_earthdata
    from downloaders.orbit_downloader import download_orbit_files
    from utils.registry import (
        fix_load_sar_registry, 
        check_scene_overlap,
        update_registry_atomic_fixed
    )
    from utils.geometry import get_sentinel_scene_extents
    from utils.date_utils import extract_scene_date
    from utils.logging import log_tiff_processing
    
    import json
    import glob
    import rasterio
    import tempfile
    import concurrent.futures
    import threading
    import asf_search as asf
    from datetime import timedelta
    
    logger = setup_logging(config)
    
    # Create processing directories
    config.create_directories()
    
    # Get list of TIFF files
    tiff_files = [os.path.join(config.tiff_folder, f) for f in os.listdir(config.tiff_folder) 
                  if f.lower().endswith(('.tiff', '.tif'))]
    
    if not tiff_files:
        logger.error(f"No TIFF files found in {config.tiff_folder}")
        return
    
    logger.info(f"Found {len(tiff_files)} TIFF files to process")
    
    # Create processing log
    processing_log = os.path.join(config.output_dir, 'processing_log.json')
    log_data = {
        'start_time': datetime.now().isoformat(),
        'total_scenes': len(tiff_files),
        'config': config.__dict__,
        'logs_directory': os.path.join(config.output_dir, 'logs'),
        'jobs': []
    }
    
    def process_single_scene(tiff_file, gpu_id):
        """Process a single TIFF file"""
        try:
            logger.info(f"Processing {tiff_file} on GPU {gpu_id}")
            base_name = os.path.splitext(os.path.basename(tiff_file))[0]
            
            # Determine disaster phase from filename
            disaster_phase = None
            if 'pre_disaster' in base_name:
                disaster_phase = 'pre_disaster'
            elif 'post_disaster' in base_name:
                disaster_phase = 'post_disaster'
            else:
                # Try to infer from parent directory name
                parent_dir = os.path.basename(os.path.dirname(tiff_file))
                if 'pre' in parent_dir.lower():
                    disaster_phase = 'pre_disaster'
                elif 'post' in parent_dir.lower():
                    disaster_phase = 'post_disaster'
                
            logger.info(f"Detected disaster phase: {disaster_phase or 'unknown'}")
        
            # Create output directories
            dirs = {
                'dem': os.path.join(config.output_dir, 'dem', base_name),
                'orbit': os.path.join(config.output_dir, 'orbit', base_name),
                'raw': os.path.join(config.output_dir, 'raw', base_name),
                'rtc': os.path.join(config.output_dir, 'rtc', base_name),
                'final': os.path.join(config.output_dir, 'final')
            }
            
            for dir_path in dirs.values():
                os.makedirs(dir_path, exist_ok=True)

            # Get MAXAR metadata and bounds
            with rasterio.open(tiff_file) as src:
                bounds = src.bounds
                maxar_bounds = (bounds.left, bounds.bottom, bounds.right, bounds.top)
            
            json_file = os.path.join(config.label_folder, f"{base_name}.json")
            if not os.path.exists(json_file):
                raise FileNotFoundError(f"JSON metadata file not found: {json_file}")
                
            with open(json_file) as f:
                metadata = json.load(f)
                maxar_date = datetime.fromisoformat(
                    metadata['metadata']['capture_date'].replace('Z', '+00:00')
                )

            # Check for existing processing
            sar_registry = fix_load_sar_registry(config.output_dir)
            matching_scene, existing_files = check_scene_overlap(
                maxar_bounds, 
                sar_registry, 
                disaster_phase,
                maxar_date,
                tolerance=config.tolerance,
                date_tolerance_days=config.date_tolerance_days
            )
            
            final_output = os.path.join(dirs['final'], f"{base_name}_RTC_clipped.tif")
            
            if matching_scene and existing_files:
                logger.info(f"Found existing matching scene: {matching_scene}")
                
                if not os.path.exists(final_output):
                    vv_file = existing_files.get('vv')
                    vh_file = existing_files.get('vh')
                    
                    if vv_file and vh_file and os.path.exists(vv_file) and os.path.exists(vh_file):
                        clip_and_merge_rtc_output(vv_file, vh_file, tiff_file, final_output)
                        
                        # Update registry with this MAXAR chip
                        if matching_scene in sar_registry:
                            maxar_processed_files = {'clipped': final_output}
                            update_registry_atomic_fixed(
                                config.output_dir,
                                matching_scene,
                                sar_registry[matching_scene].get('sentinel_bounds', [0, 0, 0, 0]),
                                maxar_bounds,
                                maxar_processed_files,
                                base_name,
                                disaster_phase,
                                None
                            )
                
                return {
                    'tiff_file': tiff_file,
                    'status': 'reused',
                    'matching_scene': matching_scene,
                    'output_file': final_output,
                    'disaster_phase': disaster_phase
                }
            
            # Download DEM
            logger.info("Downloading DEM...")
            dem_file = download_srtm_earthdata(
                maxar_bounds,
                dirs['dem'],
                config.earthdata_username,
                config.earthdata_password,
                buffer_degrees=config.buffer_degrees
            )
            
            # Search for Sentinel data
            logger.info("Searching for Sentinel-1 data...")
            search_range = (maxar_date - timedelta(days=config.search_days), 
                          maxar_date + timedelta(days=config.search_days))
            
            # Create WKT for search
            from utils.geometry import create_wkt_from_bounds
            wkt_extent = create_wkt_from_bounds(maxar_bounds)
            
            # Search for scenes
            sentinel_results = asf.geo_search(
                platform="Sentinel-1",
                processingLevel="SLC",
                beamMode="IW",
                start=search_range[0],
                end=search_range[1],
                intersectsWith=wkt_extent
            )
            
            if not sentinel_results:
                raise RuntimeError("No suitable Sentinel scenes found")
            
            # Select best scene (closest in time)
            best_scene = None
            min_time_diff = timedelta(days=365)
            
            for scene in sentinel_results:
                props = scene.properties
                if 'sceneName' not in props or 'startTime' not in props:
                    continue
                    
                scene_name = props['sceneName']
                
                # Skip OPERA/CSLC products and ensure SLC
                if 'OPERA' in scene_name or 'CSLC' in scene_name:
                    continue
                if not ('SLC' in scene_name and 'IW' in scene_name):
                    continue
                
                # Check polarization
                polarization = props.get('polarization', '')
                if config.polarization_required == "dual-pol" and not ('+' in polarization and 
                                                                      all(pol in polarization for pol in ['VV', 'VH'])):
                    continue
                    
                scene_date = datetime.fromisoformat(props['startTime'].replace('Z', '+00:00'))
                time_diff = abs(scene_date - maxar_date)
                
                if time_diff < min_time_diff:
                    min_time_diff = time_diff
                    best_scene = scene
            
            if not best_scene:
                raise RuntimeError("No suitable Sentinel scene found with required polarization")
            
            scene_id = best_scene.properties['sceneName']
            logger.info(f"Selected scene: {scene_id}")
            
            # Download Sentinel data
            safe_file = os.path.join(dirs['raw'], f"{scene_id}.zip")
            
            if not os.path.exists(safe_file):
                logger.info("Downloading Sentinel-1 data...")
                downloader = bulk_downloader(
                    username=config.earthdata_username,
                    password=config.earthdata_password
                )
                downloader.files = [best_scene.properties['url']]
                downloaded = downloader.download_files(dirs['raw'])
                safe_file = downloaded[0]
            
            # Get Sentinel scene extents
            sentinel_bounds = get_sentinel_scene_extents(safe_file)
            
            # Download orbit files
            logger.info("Downloading orbit files...")
            orbit_files = download_orbit_files(
                {'sceneName': scene_id},
                dirs['orbit'],
                config.earthdata_username,
                config.earthdata_password
            )
            
            # Generate RTC configuration
            logger.info("Generating RTC configuration...")
            product_id = f"RTC_S1_{base_name}_{maxar_date.strftime('%Y%m%d')}"
            config_yaml = generate_rtc_runconfig(
                safe_file,
                dirs['rtc'],
                dem_file,
                orbit_files,
                product_id
            )
            
            # Create and run RTC processing script
            logger.info("Running RTC processing...")
            script_path = create_slurm_job_script(
                scene_id=scene_id,
                config_path=config_yaml,
                output_dir=dirs['rtc'],
                gpu_id=gpu_id
            )
            
            run_rtc_processing(script_path, dirs['rtc'])
            
            # Find output files
            vv_files = glob.glob(os.path.join(dirs['rtc'], '*VV*.tif'))
            vh_files = glob.glob(os.path.join(dirs['rtc'], '*VH*.tif'))
            
            if not vv_files:
                raise RuntimeError("RTC output VV file not found")
            
            vv_file = vv_files[0]
            vh_file = vh_files[0] if vh_files else vv_file  # Use VV for both if single-pol
            
            # Register the processed scene
            processed_files = {
                'vv': vv_file,
                'vh': vh_file,
                'dem': dem_file,
                'safe': safe_file,
                'orbit': orbit_files[0]
            }
            
            # Create final clipped output
            logger.info("Creating final clipped output...")
            clip_and_merge_rtc_output(vv_file, vh_file, tiff_file, final_output)
            
            # Update processed files to include clipped output
            maxar_processed_files = processed_files.copy()
            maxar_processed_files['clipped'] = final_output
            
            # Register in registry
            sentinel_date = datetime.fromisoformat(
                best_scene.properties['startTime'].replace('Z', '+00:00')
            )
            
            update_success = update_registry_atomic_fixed(
                config.output_dir,
                scene_id,
                sentinel_bounds,
                maxar_bounds,
                processed_files,
                base_name,
                disaster_phase,
                sentinel_date
            )
            
            if not update_success:
                logger.warning(f"Failed to update registry for {scene_id}")
            
            # Clean up raw files to save space
            try:
                logger.info("Cleaning up raw files...")
                for raw_file in glob.glob(os.path.join(dirs['raw'], '*.zip')):
                    if os.path.exists(raw_file):
                        os.remove(raw_file)
                
                if os.path.exists(dirs['raw']) and not os.listdir(dirs['raw']):
                    os.rmdir(dirs['raw'])
            except Exception as e:
                logger.warning(f"Error during cleanup: {e}")
            
            return {
                'tiff_file': tiff_file,
                'status': 'completed',
                'output_file': final_output,
                'sentinel_id': scene_id,
                'disaster_phase': disaster_phase,
                'sentinel_date': sentinel_date.isoformat(),
                'maxar_date': maxar_date.isoformat()
            }
                   
        except Exception as e:
            logger.error(f"Error processing {tiff_file}: {str(e)}")
            return {
                'tiff_file': tiff_file,
                'status': 'failed',
                'error': str(e)
            }
    
    # Process scenes in parallel
    gpu_semaphores = [threading.Semaphore(1) for _ in range(config.max_concurrent_jobs)]
    
    def process_with_gpu(tiff_file, gpu_id):
        with gpu_semaphores[gpu_id]:
            return process_single_scene(tiff_file, gpu_id)
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=config.max_concurrent_jobs) as executor:
        futures = {}
        for i, tiff_file in enumerate(tiff_files):
            gpu_id = i % config.max_concurrent_jobs
            future = executor.submit(process_with_gpu, tiff_file, gpu_id)
            futures[future] = tiff_file
        
        # Process results as they complete
        for future in concurrent.futures.as_completed(futures):
            tiff_file = futures[future]
            try:
                result = future.result()
                log_data['jobs'].append(result)
                
                # Update processing log atomically
                with tempfile.NamedTemporaryFile(mode='w', delete=False, 
                                               dir=os.path.dirname(processing_log)) as temp_file:
                    json.dump(log_data, temp_file, indent=2)
                    temp_file_name = temp_file.name
                
                os.replace(temp_file_name, processing_log)
                
            except Exception as e:
                error_msg = f"Error processing {os.path.basename(tiff_file)}: {str(e)}"
                logger.error(error_msg)
                log_data['jobs'].append({
                    'tiff_file': tiff_file,
                    'status': 'failed',
                    'error': str(e)
                })
    
    # Create summary
    success_count = sum(1 for job in log_data['jobs'] if job['status'] in ['completed', 'reused'])
    failed_count = sum(1 for job in log_data['jobs'] if job['status'] == 'failed')
    
    logger.info(f"Processing complete. Success: {success_count}, Failed: {failed_count}")
    
    # Validate registry if requested
    if config.validate_registry:
        logger.info("Validating registry...")
        validate_sar_registry(config.output_dir)


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(description='SAR Disaster Processing Pipeline')
    
    # Config options
    parser.add_argument('--config', '-c', help='Configuration file path (YAML or JSON)')
    parser.add_argument('--create-config', help='Create default configuration file at specified path')
    parser.add_argument('--use-env', action='store_true', help='Use environment variables for configuration')
    
    # Direct parameter options (override config file)
    parser.add_argument('--tiff-folder', help='Input TIFF folder')
    parser.add_argument('--label-folder', help='Label folder')
    parser.add_argument('--output-dir', help='Output directory')
    parser.add_argument('--earthdata-username', help='NASA Earthdata username')
    parser.add_argument('--earthdata-password', help='NASA Earthdata password')
    parser.add_argument('--max-jobs', type=int, help='Maximum concurrent jobs')
    
    # Registry management
    parser.add_argument('--validate-registry', action='store_true', help='Validate registry')
    parser.add_argument('--rebuild-registry', action='store_true', help='Rebuild registry from existing files')
    
    args = parser.parse_args()
    
    # Handle special commands first
    if args.create_config:
        create_default_config_file(args.create_config)
        return
    
    if args.rebuild_registry:
        if not args.output_dir and not args.config:
            parser.error("--rebuild-registry requires --output-dir or --config")
        output_dir = args.output_dir
        if args.config:
            config = load_config(args.config)
            output_dir = config.output_dir
        rebuild_sar_registry(output_dir)
        return
    
    if args.validate_registry:
        if not args.output_dir and not args.config:
            parser.error("--validate-registry requires --output-dir or --config")
        output_dir = args.output_dir
        if args.config:
            config = load_config(args.config)
            output_dir = config.output_dir
        validate_sar_registry(output_dir)
        return
    
    # Load configuration
    try:
        config = load_config(args.config, args.use_env)
    except ValueError as e:
        parser.error(str(e))
    
    # Override config with command line arguments
    if args.tiff_folder:
        config.tiff_folder = args.tiff_folder
    if args.label_folder:
        config.label_folder = args.label_folder
    if args.output_dir:
        config.output_dir = args.output_dir
    if args.earthdata_username:
        config.earthdata_username = args.earthdata_username
    if args.earthdata_password:
        config.earthdata_password = args.earthdata_password
    if args.max_jobs:
        config.max_concurrent_jobs = args.max_jobs
    
    # Validate required parameters
    if not all([config.tiff_folder, config.label_folder, config.output_dir, 
                config.earthdata_username, config.earthdata_password]):
        parser.error("Missing required parameters. Use --config file or provide all required arguments.")
    
    # Run processing
    try:
        process_scenes(config)
    except KeyboardInterrupt:
        print("\nProcessing interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"Error during processing: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()