"""
Orbit file downloader for Sentinel-1 processing.
"""

import os
import requests
from datetime import datetime
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from ..utils.date_utils import extract_scene_date


def download_orbit_files(safe_metadata, output_dir, earthdata_username, earthdata_password, max_retries=3):
    """Download orbit files with robust error handling and retry mechanism"""
    os.makedirs(output_dir, exist_ok=True)
    
    # Get scene date
    scene_name = safe_metadata.get('sceneName', '')
    scene_date = extract_scene_date(scene_name)
    
    # Set up authentication
    auth = (earthdata_username, earthdata_password)
    
    # Create a session with retry capabilities
    session = requests.Session()
    retry_strategy = Retry(
        total=max_retries,
        backoff_factor=0.5,  # Exponential backoff
        status_forcelist=[500, 502, 503, 504],  # Retry on these status codes
        allowed_methods=["GET"]  # Replace method_whitelist with allowed_methods
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    
    # First authenticate with Earthdata Login
    auth_url = "https://urs.earthdata.nasa.gov/oauth/authorize"
    auth_params = {
        "client_id": "BO_n7nTIlMljdvU6kRRB3g",
        "response_type": "code",
        "redirect_uri": "https://auth.asf.alaska.edu/login"
    }
    
    try:
        # Authenticate and get cookies
        session.get(auth_url, params=auth_params, auth=auth, verify=False)
        
        # Try POEORB first, then RESORB
        for orbit_type in ['POEORB', 'RESORB']:
            base_url = f"https://s1qc.asf.alaska.edu/aux_{orbit_type.lower()}/"
            
            try:
                # Get file listing with timeout and retry
                response = session.get(base_url, verify=False, timeout=30)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.text, 'html.parser')
                orbit_files = [link.get('href') for link in soup.find_all('a') 
                             if link.get('href', '').endswith('.EOF')]
                
                # Find matching orbit file
                for file_name in orbit_files:
                    if scene_name[:3] not in file_name:
                        continue
                        
                    try:
                        v_start_str = file_name.split('_V')[1][:15]
                        v_end_str = file_name.split('_V')[1][16:31]
                        v_start = datetime.strptime(v_start_str, "%Y%m%dT%H%M%S")
                        v_end = datetime.strptime(v_end_str, "%Y%m%dT%H%M%S")
                        
                        if v_start <= scene_date <= v_end:
                            # Download file with retry
                            file_url = f"{base_url}{file_name}"
                            output_path = os.path.join(output_dir, file_name)
                            
                            try:
                                # Use streaming download with timeout
                                with session.get(file_url, verify=False, stream=True, timeout=60) as response:
                                    response.raise_for_status()
                                    with open(output_path, 'wb') as f:
                                        for chunk in response.iter_content(chunk_size=8192):
                                            if chunk:
                                                f.write(chunk)
                                
                                print(f"Successfully downloaded orbit file: {file_name}")
                                return [output_path]
                            
                            except requests.exceptions.RequestException as e:
                                print(f"Download failed for {file_name}: {e}")
                                continue
                        
                    except Exception as e:
                        print(f"Error processing orbit file {file_name}: {e}")
                        continue
            
            except requests.exceptions.RequestException as e:
                print(f"Error fetching orbit files for {orbit_type}: {e}")
                continue
    
    except requests.exceptions.RequestException as e:
        print(f"Authentication or network error: {e}")
        if hasattr(e, 'response'):
            print(f"Response status code: {e.response.status_code}")
            print(f"Response content: {e.response.text}")
    
    raise RuntimeError(f"No matching orbit files found for scene: {scene_name}")