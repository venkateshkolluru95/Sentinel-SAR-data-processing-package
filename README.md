# SAR Data Processing Pipeline

A comprehensive Python package for processing Synthetic Aperture Radar (SAR) data with Radiometric Terrain Correction (RTC), specifically designed to download Sentinel-1 data that aligns with input reference images. It includes functionalities for downloading SRTM DEMs, acquiring Sentinel-1 data and orbit files, processing RTC, and validating results.

## Overview

This package provides an automated pipeline for:
- **Automated SAR Processing**: End-to-end processing of Sentinel-1 SLC data using NASA's RTC workflow
- **Multi-sensor Integration**: Combines SAR and optical (MAXAR) data for comprehensive disaster analysis  
- **Scene Registry**: Intelligent tracking of processed scenes to avoid redundant processing
- **Parallel Processing**: GPU-accelerated processing with configurable concurrency
- **Flexible Configuration**: YAML/JSON configuration files with CLI override options
- **Comprehensive Logging**: Individual file logging with centralized processing logs
- **Data Downloads**: Automated downloading of Sentinel-1, SRTM DEM, and orbit files
- **Quality Control**: Extensive validation and error handling throughout the pipeline

## Installation

## Prerequisites

### Required Python Packages
```
rasterio>=1.3.0
gdal>=3.4.0
numpy>=1.21.0
asf-search>=6.0.0
requests>=2.28.0
urllib3>=1.26.0
beautifulsoup4>=4.11.0
pyyaml>=6.0
click>=8.0.0
python-dateutil>=2.8.0
```

### External Requirements
- **Python 3.8+**
- **GDAL 3.4+** with Python bindings
- **CUDA-capable GPU** (for RTC processing)
- **NASA Earthdata account** credentials
- **Conda environment** with RTC package installed
- **Access to ASF** (Alaska Satellite Facility) data

### RTC Processing Component

The Radiometric Terrain Correction (RTC) processing component used in this package is from the OPERA RTC project developed by NASA's Jet Propulsion Laboratory (JPL). 

**Installation Requirements:**

1. Install ISCE3:
```bash
conda install -c conda-forge isce3
```

2. Install s1-reader:
```bash
git clone https://github.com/opera-adt/s1-reader.git s1-reader
conda install -c conda-forge --file s1-reader/requirements.txt
python -m pip install ./s1-reader
```

3. Install RTC:
```bash
git clone https://github.com/opera-adt/RTC.git RTC
python -m pip install ./RTC
```

**Original Projects:**
- Repository: [opera-adt/RTC](https://github.com/opera-adt/RTC)
- Fork used: [gshiroma/RTC](https://github.com/gshiroma/RTC)

## Installation

1. **Clone the repository**:
```bash
git clone https://github.com/yourusername/sar-disaster-processing.git
cd sar-disaster-processing
```

2. **Install Python dependencies**:
```bash
pip install -r requirements.txt
```

3. **Set up conda environment for RTC processing**:
```bash
conda create -n s1rtc
conda activate s1rtc
# Install ISCE3, s1-reader, and RTC as described in Prerequisites
```

4. **Set up NASA Earthdata credentials**:
```bash
export EARTHDATA_USERNAME="your_username"
export EARTHDATA_PASSWORD="your_password"
```

### Directory Structure
The pipeline expects/creates the following directory structure:
```
output_base_dir/
├── dem/                     # Digital Elevation Model files per scene
├── orbit/                   # Orbit files per scene  
├── raw/                     # Raw Sentinel-1 downloads (cleaned up after processing)
├── rtc/                     # RTC processing outputs per scene
├── final/                   # Final clipped outputs
├── logs/                    # Individual processing logs
├── sar_registry.json        # Scene processing registry
└── processing_log.json      # Overall processing log
```

## Quick Start

1. **Create a configuration file**:
```bash
python main.py --create-config config.yaml
```

2. **Edit the configuration** with your specific paths and settings.

3. **Run the processing pipeline**:
```bash
python main.py --config config.yaml
```

## Configuration

### Configuration File Example (`config.yaml`)

```yaml
# Required paths
output_dir: "/path/to/output"
tiff_folder: "/path/to/maxar/tiffs"
label_folder: "/path/to/maxar/labels"

# Credentials
earthdata_username: "your_username"
earthdata_password: "your_password"

# Processing parameters
max_concurrent_jobs: 2
search_days: 90
polarization_required: "dual-pol"  # or "single-pol"

# Quality control
tolerance: 0.01
date_tolerance_days: 30
buffer_degrees: 2.0

# Logging
log_level: "INFO"
save_individual_logs: true
```

### Environment Variables

Alternatively, you can use environment variables:

```bash
export SAR_OUTPUT_DIR="/path/to/output"
export SAR_TIFF_FOLDER="/path/to/maxar/tiffs"
export SAR_LABEL_FOLDER="/path/to/maxar/labels"
export EARTHDATA_USERNAME="your_username"
export EARTHDATA_PASSWORD="your_password"
export SAR_MAX_JOBS="2"
```

Then run with:
```bash
python main.py --use-env
```

## Usage

### Basic Usage Example

```python
# Using the main CLI
python main.py --config config.yaml

# Or using the package directly
from config.settings import ProcessingConfig, load_config

# Load configuration
config = load_config("config.yaml")

# Process scenes (main processing function)
from main import process_scenes
process_scenes(config)
```

### Command Line Interface

```bash
# Create config template
python main.py --create-config config.yaml

# Process with configuration file
python main.py --config config.yaml

# Process with environment variables
python main.py --use-env

# Process with direct CLI arguments
python main.py \
    --tiff-folder /path/to/tiffs \
    --label-folder /path/to/labels \
    --output-dir /path/to/output \
    --earthdata-username your_username \
    --earthdata-password your_password \
    --max-jobs 2

# Registry management
python main.py --validate-registry --output-dir /path/to/output
python main.py --rebuild-registry --output-dir /path/to/output
```

## Main Components

### 1. **Configuration Management** (`config/`)
- **ProcessingConfig**: Centralized configuration with validation
- **Multiple input methods**: YAML/JSON files, environment variables, CLI arguments
- **Parameter validation**: Ensures all required settings are present and valid

### 2. **Data Downloaders** (`downloaders/`)
- **bulk_downloader**: Authenticated downloads from NASA Earthdata/ASF
- **dem_downloader**: SRTM DEM tile downloading and mosaicking  
- **orbit_downloader**: Precise orbit file acquisition for Sentinel-1

### 3. **Processing Pipeline** (`processors/`)
- **rtc_config**: RTC configuration generation and SLURM job management
- **output_processor**: Post-processing, clipping, and band merging

### 4. **Utilities** (`utils/`)
- **registry**: SAR scene registry management with atomic operations
- **logging**: Comprehensive logging with individual file tracking
- **geometry**: Spatial utilities and coordinate transformations
- **date_utils**: Date parsing and validation functions

### 5. **SAR Registry System**
- **Scene tracking**: JSON-based registry of processed SAR scenes
- **Overlap detection**: Prevents redundant processing by checking scene coverage
- **Atomic updates**: Thread-safe registry modifications with retry logic
- **Validation**: Ensures registry integrity and file existence

### 6. **Quality Control and Validation**
- **File validation**: Comprehensive checks for data integrity
- **Processing status tracking**: Detailed logging of all processing events
- **Error recovery**: Robust error handling with detailed reporting
- **Registry validation**: Ensures processed files are correctly registered

## Package Structure

```
Sentinel_SAR_processing/
├── __init__.py                    # Package initialization
├── main.py                        # Main CLI entry point
├── version.py                     # Version information
├── requirements.txt               # Dependencies
├── readme.md                      # Documentation
├── config/
│   └── settings.py               # Configuration management
├── downloaders/
│   ├── __init__.py
│   ├── bulk_downloader.py        # Sentinel-1 ASF downloader
│   ├── dem_downloader.py         # SRTM DEM downloader
│   └── orbit_downloader.py       # Orbit file downloader
├── processors/
│   ├── __init__.py
│   ├── rtc_config.py            # RTC configuration & execution
│   └── output_processor.py      # Clipping & merging
└── utils/
    ├── __init__.py
    ├── imports.py               # Common imports
    ├── logging.py               # Logging utilities
    ├── date_utils.py            # Date parsing
    ├── geometry.py              # Spatial utilities
    └── registry.py              # Scene registry management
```

## Processing Flow

1. **Initialization**
   - Load configuration from file, environment, or CLI arguments
   - Load SAR registry to check for existing processed scenes
   - Create output directories and set up logging
   - Validate input parameters and credentials

2. **For each TIFF file**
   - Extract MAXAR metadata and geographic bounds
   - Determine disaster phase (pre/post disaster) from filename
   - Check registry for existing processed scenes covering the same area
   - If matching scene found, reuse existing data and create clipped output
   - If no match found, proceed with full processing:

3. **Data Acquisition**
   - Download SRTM DEM tiles covering the area of interest
   - Search for matching Sentinel-1 SLC scenes within date range
   - Select best scene based on temporal proximity and polarization
   - Download selected Sentinel-1 scene and orbit files

4. **RTC Processing**
   - Generate RTC configuration YAML file
   - Create SLURM job script for GPU processing
   - Execute RTC processing using NASA's workflow
   - Validate output VV and VH polarization files

5. **Post-Processing**
   - Clip RTC outputs to match MAXAR image bounds
   - Merge VV and VH bands into single output file
   - Reproject to WGS84 coordinate system
   - Create final processed output in standardized format

6. **Quality Control and Registry Management**
   - Validate all processed files for completeness and integrity
   - Register processed scene in atomic registry operation
   - Log processing events and status information
   - Clean up temporary and raw data files to save disk space

7. **Error Handling and Recovery**
   - Comprehensive error logging with detailed stack traces
   - Processing continues with remaining files if individual files fail
   - Registry integrity maintained even with processing failures
   - Detailed status reporting for troubleshooting

## Important Notes

1. **Permissions**: Set appropriate permissions for script execution
2. **Disk Space**: Ensure sufficient disk space for processing (RTC outputs can be large)
3. **Credentials**: Verify NASA Earthdata credentials are correctly configured
4. **Environment**: Check RTC conda environment setup and GPU availability
5. **Monitoring**: Monitor processing logs for errors and resource usage
6. **Network**: Stable internet connection required for data downloads
7. **Dependencies**: Ensure all external dependencies (GDAL, ISCE3, etc.) are properly installed

## Error Handling

The pipeline includes comprehensive error handling:
- **File validation checks** at every processing stage
- **Processing status logging** with detailed event tracking
- **Scene overlap verification** to prevent redundant processing
- **Data integrity validation** for all downloaded and processed files
- **Detailed error reporting** with full stack traces
- **Graceful failure handling** - processing continues even if individual files fail
- **Atomic registry operations** to maintain data consistency
- **Resource cleanup** even when errors occur

## Logging

Processing events are logged in multiple formats:
- **Individual file logs**: Each TIFF file gets its own detailed log in `logs/` directory
- **Central processing log**: Overall status in JSON format (`processing_log.json`)
- **Registry tracking**: Scene processing history in `sar_registry.json`
- **Console output**: Real-time progress information
- **Event categorization**: PROCESSED, ERROR, SKIPPED, REUSED status types

Log files include:
- Timestamp information
- File paths and metadata
- Processing parameters
- Error messages and stack traces
- Resource usage information
- Processing duration

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Submit a pull request

### RTC License

The RTC component is licensed under the following terms:

Copyright (c) 2021 California Institute of Technology ("Caltech"). U.S. Government sponsorship acknowledged.

All rights reserved.

Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:
- Redistributions of source code must retain the above copyright notice
- Redistributions in binary form must reproduce the above copyright notice
- Neither Caltech, JPL, nor contributor names may be used to endorse or promote products without permission

Full license terms can be found in the original repository.

## Acknowledgments

- Alaska Satellite Facility (ASF)
- NASA Earthdata
- SRTM Data providers
- NASA's Jet Propulsion Laboratory (JPL) OPERA Algorithm Development Team for the RTC processing component
- California Institute of Technology

## Support

For questions and support:
- Create an issue on GitHub
- Email: vk0046@uah.edu

## Citation

```
