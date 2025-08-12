"""
Configuration settings for SAR processing pipeline.
"""

import os
import yaml
import json
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass
class ProcessingConfig:
    """Configuration for SAR processing"""
    
    # Required paths
    output_dir: str
    tiff_folder: str = ""
    label_folder: str = ""
    
    # Optional paths
    temp_dir: Optional[str] = None
    
    # Credentials
    earthdata_username: str = ""
    earthdata_password: str = ""
    
    # Processing parameters
    max_concurrent_jobs: int = 2
    gpu_ids: List[int] = field(default_factory=lambda: [0])
    search_days: int = 90
    buffer_degrees: float = 2.0
    
    # Quality control
    min_scene_overlap: float = 0.8
    max_cloud_cover: float = 20.0
    tolerance: float = 0.01
    date_tolerance_days: int = 30
    
    # RTC processing
    polarization_required: str = "dual-pol"  # "dual-pol" or "single-pol"
    dem_upsampling: int = 1
    geogrid_posting: int = 10  # meters
    
    # Registry settings
    validate_registry: bool = True
    rebuild_registry: bool = False
    
    # Logging
    log_level: str = "INFO"
    save_individual_logs: bool = True
    
    def __post_init__(self):
        """Validate configuration after initialization"""
        self._validate_config()
    
    def _validate_config(self):
        """Validate configuration parameters"""
        if not self.output_dir:
            raise ValueError("output_dir is required")
        
        if self.max_concurrent_jobs < 1:
            raise ValueError("max_concurrent_jobs must be at least 1")
        
        if self.search_days < 1:
            raise ValueError("search_days must be at least 1")
        
        if self.polarization_required not in ["dual-pol", "single-pol"]:
            raise ValueError("polarization_required must be 'dual-pol' or 'single-pol'")
        
        if self.log_level not in ["DEBUG", "INFO", "WARNING", "ERROR"]:
            raise ValueError("log_level must be one of: DEBUG, INFO, WARNING, ERROR")
    
    @classmethod
    def from_env(cls) -> 'ProcessingConfig':
        """Load configuration from environment variables"""
        return cls(
            output_dir=os.environ.get('SAR_OUTPUT_DIR', ''),
            tiff_folder=os.environ.get('SAR_TIFF_FOLDER', ''),
            label_folder=os.environ.get('SAR_LABEL_FOLDER', ''),
            temp_dir=os.environ.get('SAR_TEMP_DIR'),
            earthdata_username=os.environ.get('EARTHDATA_USERNAME', ''),
            earthdata_password=os.environ.get('EARTHDATA_PASSWORD', ''),
            max_concurrent_jobs=int(os.environ.get('SAR_MAX_JOBS', '2')),
            search_days=int(os.environ.get('SAR_SEARCH_DAYS', '90')),
            log_level=os.environ.get('SAR_LOG_LEVEL', 'INFO')
        )
    
    @classmethod
    def from_file(cls, config_path: str) -> 'ProcessingConfig':
        """Load configuration from YAML or JSON file"""
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Configuration file not found: {config_path}")
        
        with open(config_path, 'r') as f:
            if config_path.endswith('.yaml') or config_path.endswith('.yml'):
                data = yaml.safe_load(f)
            elif config_path.endswith('.json'):
                data = json.load(f)
            else:
                raise ValueError("Configuration file must be YAML or JSON")
        
        return cls(**data)
    
    def to_file(self, config_path: str):
        """Save configuration to YAML or JSON file"""
        config_dict = {
            'output_dir': self.output_dir,
            'tiff_folder': self.tiff_folder,
            'label_folder': self.label_folder,
            'temp_dir': self.temp_dir,
            'earthdata_username': self.earthdata_username,
            'earthdata_password': self.earthdata_password,
            'max_concurrent_jobs': self.max_concurrent_jobs,
            'gpu_ids': self.gpu_ids,
            'search_days': self.search_days,
            'buffer_degrees': self.buffer_degrees,
            'min_scene_overlap': self.min_scene_overlap,
            'max_cloud_cover': self.max_cloud_cover,
            'tolerance': self.tolerance,
            'date_tolerance_days': self.date_tolerance_days,
            'polarization_required': self.polarization_required,
            'dem_upsampling': self.dem_upsampling,
            'geogrid_posting': self.geogrid_posting,
            'validate_registry': self.validate_registry,
            'rebuild_registry': self.rebuild_registry,
            'log_level': self.log_level,
            'save_individual_logs': self.save_individual_logs
        }
        
        with open(config_path, 'w') as f:
            if config_path.endswith('.yaml') or config_path.endswith('.yml'):
                yaml.dump(config_dict, f, default_flow_style=False, indent=2)
            elif config_path.endswith('.json'):
                json.dump(config_dict, f, indent=2)
            else:
                raise ValueError("Configuration file must be YAML or JSON")
    
    def get_credentials(self) -> Dict[str, str]:
        """Get earthdata credentials as dictionary"""
        return {
            'username': self.earthdata_username,
            'password': self.earthdata_password
        }
    
    def create_directories(self):
        """Create necessary output directories"""
        dirs_to_create = [
            self.output_dir,
            os.path.join(self.output_dir, 'dem'),
            os.path.join(self.output_dir, 'orbit'),
            os.path.join(self.output_dir, 'raw'),
            os.path.join(self.output_dir, 'rtc'),
            os.path.join(self.output_dir, 'final'),
            os.path.join(self.output_dir, 'logs')
        ]
        
        if self.temp_dir:
            dirs_to_create.append(self.temp_dir)
        
        for directory in dirs_to_create:
            os.makedirs(directory, exist_ok=True)


# Default configuration template
DEFAULT_CONFIG = ProcessingConfig(
    output_dir="/path/to/output",
    tiff_folder="/path/to/tiff/files",
    label_folder="/path/to/label/files",
    earthdata_username="your_username",
    earthdata_password="your_password"
)


def create_default_config_file(output_path: str):
    """Create a default configuration file template"""
    DEFAULT_CONFIG.to_file(output_path)
    print(f"Created default configuration file at: {output_path}")
    print("Please edit the file with your specific settings before running the pipeline.")


def load_config(config_path: Optional[str] = None, 
                use_env: bool = False) -> ProcessingConfig:
    """
    Load configuration with fallback options
    
    Args:
        config_path: Path to configuration file
        use_env: Whether to use environment variables
    
    Returns:
        ProcessingConfig instance
    """
    if config_path and os.path.exists(config_path):
        config = ProcessingConfig.from_file(config_path)
        print(f"Loaded configuration from: {config_path}")
    elif use_env:
        config = ProcessingConfig.from_env()
        print("Loaded configuration from environment variables")
    else:
        raise ValueError(
            "No valid configuration found. Please provide a config file or set use_env=True"
        )
    
    # Create output directories
    config.create_directories()
    
    return config