"""
RTC configuration and processing utilities.
"""

import os
import yaml
import subprocess
import threading
import traceback


def generate_rtc_runconfig(safe_file, output_dir, dem_file, orbit_files, product_id):
    """Generate RTC configuration YAML with valid settings matched to the data."""
    # Determine polarization from filename
    polarization = "single-pol"  # Default to single-pol
    if "_1SDV_" in safe_file:
        polarization = "dual-pol"
    else:
        # For more precise determination, we could read the file metadata
        # But this simple check should cover most cases
        if "_1SSV_" in safe_file:
            polarization = "single-pol"
    
    print(f"Detected polarization from filename: {polarization}")
    
    config = {
        'runconfig': {
            'name': 'rtc_s1_workflow',
            'groups': {
                'primary_executable': {
                    'product_type': 'RTC_S1'
                },
                'pge_name_group': {
                    'pge_name': 'RTC_S1_PGE'
                },
                'input_file_group': {
                    'safe_file_path': [safe_file],
                    'orbit_file_path': orbit_files
                },
                'dynamic_ancillary_file_group': {
                    'dem_file': dem_file,
                    'dem_file_description': ''
                },
                'static_ancillary_file_group': {
                    'burst_database_file': None
                },
                'product_group': {
                    'processing_type': 'CUSTOM',
                    'product_path': '.',
                    'scratch_path': output_dir,
                    'output_dir': output_dir,
                    'product_id': product_id,
                    'save_bursts': True,
                    'save_mosaics': True,
                    'output_imagery_format': 'COG',
                    'output_imagery_compression': 'ZSTD',
                    'output_imagery_nbits': 16,
                    'save_secondary_layers_as_hdf5': False,
                    'save_metadata': False
                },
                'processing': {
                    'check_ancillary_inputs_coverage': True,
                    'polarization': polarization,  # Set based on what we detected
                    'geo2rdr': {
                        'threshold': 1.0e-8,
                        'numiter': 25
                    },
                    'rdr2geo': {
                        'threshold': 1.0e-7,
                        'numiter': 25
                    },
                    'apply_absolute_radiometric_correction': True,
                    'apply_thermal_noise_correction': True,
                    'apply_rtc': True,
                    'apply_bistatic_delay_correction': True,
                    'apply_static_tropospheric_delay_correction': True,
                    'rtc': {
                        'output_type': 'gamma0',
                        'algorithm_type': 'area_projection',
                        'input_terrain_radiometry': 'beta0',
                        'dem_upsampling': 1
                    },
                    'geocoding': {
                        'apply_valid_samples_sub_swath_masking': True,
                        'apply_shadow_masking': False,
                        'algorithm_type': 'area_projection',
                        'memory_mode': 'auto',
                        'geogrid_upsampling': 1,
                        'save_incidence_angle': False,
                        'save_local_inc_angle': True,
                        'save_projection_angle': False,
                        'save_rtc_anf_projection_angle': False,
                        'save_range_slope': False,
                        'save_nlooks': True,
                        'save_rtc_anf': True,
                        'save_rtc_anf_gamma0_to_sigma0': False,
                        'save_dem': False,
                        'save_mask': False,
                        'abs_rad_cal': 1,
                        'upsample_radargrid': False,
                        'bursts_geogrid': {
                            'output_epsg': None,
                            'x_posting': 10,
                            'y_posting': 10,
                            'x_snap': 10,
                            'y_snap': 10,
                            'top_left': {
                                'x': None,
                                'y': None
                            },
                            'bottom_right': {
                                'x': None,
                                'y': None
                            }
                        }
                    },
                    'mosaicking': {
                        'mosaic_geogrid': {
                            'output_epsg': None,
                            'x_posting': 10,
                            'y_posting': 10,
                            'x_snap': 10,
                            'y_snap': 10,
                            'top_left': {
                                'x': None,
                                'y': None
                            },
                            'bottom_right': {
                                'x': None,
                                'y': None
                            }
                        }
                    }
                }
            }
        }
    }
    
    output_yaml = os.path.join(output_dir, f"{product_id}_rtc_config.yaml")
    with open(output_yaml, 'w') as f:
        yaml.dump(config, f, default_flow_style=False)
    
    return output_yaml


def create_slurm_job_script(scene_id, config_path, output_dir, gpu_id):
    """Create SLURM job script with comprehensive environment setup and logging"""
    script = f"""#!/bin/bash
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=24:00:00

set -e  # Exit on any error

echo "=== Starting RTC Processing ==="
date
echo "Scene ID: {scene_id}"
echo "Config Path: {config_path}"
echo "Output Dir: {output_dir}"
echo "GPU ID: {gpu_id}"

# Load required modules
echo "Loading modules..."
module purge
module load cuda/12.4

# Source conda
echo "Sourcing conda..."
source /rhome/vkolluru/anaconda3/etc/profile.d/conda.sh

# Configure environment
export CUDA_VISIBLE_DEVICES={gpu_id}
export GDAL_CACHEMAX=8000
export GDAL_NUM_THREADS=8
export OMP_NUM_THREADS=8
export CUDA_FORCE_PTX_JIT=1

# Show environment
echo "=== Environment ==="
env | grep -E 'CUDA|GDAL|OMP'

# Show GPU status
echo "=== GPU Status ==="
nvidia-smi

# Monitor GPU usage
nvidia-smi dmon -i {gpu_id} -s u -d 10 &
NVIDIA_SMI_PID=$!

# Check disk space
echo "=== Disk Space ==="
df -h /rstor/vkolluru
df -h /rhome/vkolluru

# Check memory
echo "=== Memory ==="
free -h

# Change to RTC directory
echo "Changing to RTC directory..."
if [ ! -d "/rstor/vkolluru/RTC/src/rtc" ]; then
    echo "ERROR: RTC directory does not exist"
    ls -la /rstor/vkolluru/RTC/src
    exit 1
fi

cd /rstor/vkolluru/RTC/src/rtc || {{
    echo "Failed to change directory"
    exit 1
}}

# Verify current directory
echo "Current directory: $(pwd)"
ls -la

# Activate conda environment
echo "Activating conda environment..."
conda activate s1rtc || {{
    echo "Failed to activate conda environment"
    echo "Available environments:"
    conda env list
    exit 1
}}

# Display Python information
echo "Python version: $(python --version)"
echo "Python path: $(which python)"

# Verify RTC executable
if ! which rtc_s1.py &>/dev/null; then
    echo "ERROR: rtc_s1.py not found in PATH"
    echo "PATH: $PATH"
    exit 1
fi
echo "RTC executable path: $(which rtc_s1.py)"

# Check config file
if [ ! -f "{config_path}" ]; then
    echo "ERROR: Config file not found: {config_path}"
    exit 1
fi
echo "Config file content:"
cat "{config_path}"

# Clear GPU cache
echo "Clearing GPU cache..."
python -c "import torch; torch.cuda.empty_cache()"

# Run RTC processing
echo "Starting RTC processing..."
start_time=$(date +%s)

# Run with detailed verbosity 
rtc_s1.py "{config_path}" 2>&1 | tee "{output_dir}/rtc_output.log"
RTC_STATUS=$?

end_time=$(date +%s)
echo "Processing time: $((end_time-start_time)) seconds"

# Check RTC status
if [ $RTC_STATUS -ne 0 ]; then
    echo "RTC processing failed with status: $RTC_STATUS"
    echo "Directory contents of {output_dir}:"
    ls -la "{output_dir}"
    echo "Last 50 lines of the log:"
    tail -n 50 "{output_dir}/rtc_output.log"
    kill $NVIDIA_SMI_PID
    conda deactivate
    exit 1
fi

# Verify output files
echo "Checking output files..."
vv_file=$(ls "{output_dir}"/*VV*.tif 2>/dev/null || echo "")
vh_file=$(ls "{output_dir}"/*VH*.tif 2>/dev/null || echo "")

if [ -z "$vv_file" ] || [ -z "$vh_file" ]; then
    echo "Error: Output files not found"
    echo "Directory contents:"
    ls -la "{output_dir}"
    kill $NVIDIA_SMI_PID
    conda deactivate
    exit 1
fi

# Show file info
echo "=== Output Files ==="
ls -lh "$vv_file"
ls -lh "$vh_file"

# Final GPU status
echo "=== Final GPU Status ==="
nvidia-smi

# Cleanup
kill $NVIDIA_SMI_PID
conda deactivate

echo "=== Processing Completed Successfully ==="
date
"""
    
    script_path = os.path.join(output_dir, 'run_rtc.sh')
    with open(script_path, 'w') as f:
        f.write(script)
    
    os.chmod(script_path, 0o755)
    return script_path


def run_rtc_processing(script_path, output_dir):
    """Run RTC processing with comprehensive error handling and enhanced logging"""
    try:
        print("\n=== Starting RTC Processing ===")
        print(f"Script path: {script_path}")
        print(f"Output directory: {output_dir}")
        
        # Verify script exists and is executable
        if not os.path.exists(script_path):
            raise FileNotFoundError(f"RTC script not found: {script_path}")
        
        if not os.access(script_path, os.X_OK):
            raise PermissionError(f"RTC script is not executable: {script_path}")
        
        # Read script content for debugging
        with open(script_path, 'r') as f:
            print("\nScript contents:")
            print(f.read())
        
        # Create log file paths for detailed logging
        stdout_log = os.path.join(output_dir, "rtc_stdout.log")
        stderr_log = os.path.join(output_dir, "rtc_stderr.log")
        combined_log = os.path.join(output_dir, "rtc_output.log")
        
        print(f"Logging stdout to: {stdout_log}")
        print(f"Logging stderr to: {stderr_log}")
        print(f"Logging combined output to: {combined_log}")
        
        # Open log files
        with open(stdout_log, 'w') as stdout_file, open(stderr_log, 'w') as stderr_file, open(combined_log, 'w') as combined_file:
            # Configure subprocess with detailed output capture
            process = subprocess.Popen(
                ['/bin/bash', script_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env={
                    **os.environ,
                    'CUDA_VISIBLE_DEVICES': '0',
                    'GDAL_CACHEMAX': '8000',
                    'GDAL_NUM_THREADS': '8',
                    'OMP_NUM_THREADS': '8'
                },
                cwd=output_dir  # Set working directory
            )
            
            # Function to handle output streams
            def handle_output(stream, log_file, combined_file, name):
                for line in iter(stream.readline, ''):
                    print(line, end='')  # Print to console
                    log_file.write(line)  # Write to specific log file
                    log_file.flush()      # Ensure immediate write
                    combined_file.write(f"[{name}] {line}")  # Write to combined log
                    combined_file.flush() # Ensure immediate write
            
            # Create threads to handle stdout and stderr
            stdout_thread = threading.Thread(
                target=handle_output, 
                args=(process.stdout, stdout_file, combined_file, "STDOUT")
            )
            stderr_thread = threading.Thread(
                target=handle_output, 
                args=(process.stderr, stderr_file, combined_file, "STDERR")
            )
            
            # Start threads
            stdout_thread.start()
            stderr_thread.start()
            
            # Wait for threads to complete
            stdout_thread.join()
            stderr_thread.join()
            
            # Wait for process to complete
            returncode = process.wait()
        
        # Check return code
        if returncode != 0:
            print(f"\nRTC processing failed with return code: {returncode}")
            
            # Display the last 50 lines of error log for quick diagnosis
            try:
                with open(stderr_log, 'r') as f:
                    stderr_content = f.readlines()
                    if stderr_content:
                        print("\nLast 50 lines of stderr:")
                        for line in stderr_content[-50:]:
                            print(line, end='')
            except Exception as e:
                print(f"Could not read stderr log: {e}")
            
            # Check output directory contents
            print("\nOutput directory contents:")
            subprocess.run(['ls', '-la', output_dir], check=False)
            
            # Check system resources
            print("\nSystem resource status:")
            subprocess.run(['nvidia-smi'], check=False)
            subprocess.run(['free', '-h'], check=False)
            
            raise subprocess.CalledProcessError(
                returncode,
                ['/bin/bash', script_path],
                f"RTC processing failed. See logs at {stdout_log}, {stderr_log}, and {combined_log}"
            )
        
        # Verify output files exist
        print("\nChecking for output files...")
        import glob
        vv_files = glob.glob(os.path.join(output_dir, '*VV*.tif'))
        vh_files = glob.glob(os.path.join(output_dir, '*VH*.tif'))
        
        if not vv_files or not vh_files:
            print("\nOutput files not found. Directory contents:")
            subprocess.run(['ls', '-la', output_dir], check=False)
            raise RuntimeError("RTC output files not found after processing")
            
        print(f"\nFound VV file: {vv_files[0]}")
        print(f"Found VH file: {vh_files[0]}")
        
        # Validate output files
        for filepath in [vv_files[0], vh_files[0]]:
            if not os.path.exists(filepath):
                raise FileNotFoundError(f"Output file missing: {filepath}")
                
            file_size = os.path.getsize(filepath)
            if file_size == 0:
                raise ValueError(f"Output file is empty: {filepath}")
                
            print(f"Validated {os.path.basename(filepath)}: {file_size} bytes")
        
        print("\nRTC processing completed successfully")
        return True
        
    except Exception as e:
        print(f"\nError during RTC processing: {str(e)}")
        traceback.print_exc()
        raise