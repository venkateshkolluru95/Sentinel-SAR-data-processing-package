"""
Bulk downloader for Sentinel-1 data from ASF with NASA Earthdata authentication.
"""

import os
import base64
import getpass
from urllib.request import build_opener, Request, HTTPCookieProcessor, HTTPHandler, HTTPSHandler
from urllib.error import HTTPError
from http.cookiejar import MozillaCookieJar


def validate_slc_file(downloaded_file):
    """
    Validate that the downloaded file is a Sentinel-1 SLC product.
    
    Args:
        downloaded_file (str): Path to the downloaded file
    
    Returns:
        bool: True if file is a valid SLC product, False otherwise
    """
    # Check file extension
    if not downloaded_file.lower().endswith('.zip'):
        print(f"Invalid file extension: {downloaded_file}")
        return False
    
    # Check filename for SLC indicators
    filename = os.path.basename(downloaded_file)
    
    # Reject OPERA and CSLC products
    if any(invalid in filename for invalid in ['OPERA', 'CSLC']):
        print(f"Rejecting non-SLC product: {filename}")
        return False
    
    # Must be an SLC product
    if not any(slc_indicator in filename for slc_indicator in ['SLC', 'IW_SLC']):
        print(f"File does not appear to be an SLC product: {filename}")
        return False
    
    # Check file size
    try:
        file_size = os.path.getsize(downloaded_file)
        if file_size < 1024:  # Minimum file size check (1 KB)
            print(f"File size too small: {file_size} bytes")
            return False
    except Exception as e:
        print(f"Error checking file size: {e}")
        return False
    
    return True


def validate_and_filter_download(downloaded_files):
    """
    Validate downloaded files to ensure they are Sentinel-1 SLC products.
    
    Args:
        downloaded_files (list): List of downloaded file paths
    
    Returns:
        list: Validated SLC files
    """
    valid_slc_files = []
    for file_path in downloaded_files:
        filename = os.path.basename(file_path)
        
        # Check file extension
        if not filename.lower().endswith('.zip'):
            print(f"Skipping non-ZIP file: {filename}")
            if os.path.exists(file_path):
                os.remove(file_path)
            continue
        
        # Check for SLC indicators in filename
        if not any(slc_indicator in filename for slc_indicator in ['SLC', 'IW_SLC']):
            print(f"Skipping non-SLC file: {filename}")
            if os.path.exists(file_path):
                os.remove(file_path)
            continue
        
        # Reject OPERA and CSLC products
        if any(invalid in filename for invalid in ['OPERA', 'CSLC']):
            print(f"Rejecting non-SLC product: {filename}")
            if os.path.exists(file_path):
                os.remove(file_path)
            continue
        
        # Optional: Add more sophisticated checks
        try:
            file_size = os.path.getsize(file_path)
            if file_size < 1024:  # Minimum file size check (1 KB)
                print(f"Skipping small file: {filename}")
                if os.path.exists(file_path):
                    os.remove(file_path)
                continue
        except Exception as e:
            print(f"Error checking file {filename}: {e}")
            if os.path.exists(file_path):
                os.remove(file_path)
            continue
        
        valid_slc_files.append(file_path)
    
    if not valid_slc_files:
        raise RuntimeError("No valid Sentinel-1 SLC products were downloaded")
    
    return valid_slc_files


class bulk_downloader:
    """Handles authenticated downloads from NASA Earthdata with cookie management"""
    
    def __init__(self, username=None, password=None):
        self.files = []
        self.cookie_jar_path = os.path.join(
            os.path.expanduser('~'),
            ".bulk_download_cookiejar.txt"
        )
        self.cookie_jar = None
        self.asf_urs4 = {
            'url': 'https://urs.earthdata.nasa.gov/oauth/authorize',
            'client': 'BO_n7nTIlMljdvU6kRRB3g',
            'redir': 'https://auth.asf.alaska.edu/login'
        }
        self.context = {}
        self.username = username
        self.password = password
        self.get_cookie()

    def get_cookie(self):
        if os.path.isfile(self.cookie_jar_path):
            self.cookie_jar = MozillaCookieJar()
            self.cookie_jar.load(self.cookie_jar_path)
            if self.check_cookie():
                print(" > Reusing previous cookie jar.")
                return
            else:
                print(" > Could not validate old cookie Jar")

        # Try environment variables first
        if not self.username:
            self.username = os.environ.get('EARTHDATA_USERNAME')
        if not self.password:
            self.password = os.environ.get('EARTHDATA_PASSWORD')

        # If still no credentials, try to get them interactively
        while not (self.username and self.password):
            try:
                print("No existing URS cookie found, please enter Earthdata credentials:")
                print("(Credentials will not be stored, saved or logged anywhere)")
                self.username = input("Username: ")
                self.password = getpass.getpass(prompt="Password (will not be displayed): ")
            except EOFError:
                print("Error: Unable to read input. Make sure to provide credentials via environment variables when running non-interactively")
                exit(1)

        while self.check_cookie() is False:
            self.get_new_cookie()

    def check_cookie(self):
        if self.cookie_jar is None:
            print(f" > Cookiejar is bunk: {self.cookie_jar}")
            return False

        file_check = 'https://urs.earthdata.nasa.gov/profile'
        
        opener = build_opener(
            HTTPCookieProcessor(self.cookie_jar),
            HTTPHandler(),
            HTTPSHandler(**self.context)
        )
        
        from urllib.request import install_opener, urlopen
        install_opener(opener)

        request = Request(file_check)
        request.get_method = lambda : 'HEAD'
        
        try:
            response = urlopen(request, timeout=30)
            resp_code = response.getcode()
            
            if not self.check_cookie_is_logged_in(self.cookie_jar):
                return False

            self.cookie_jar.save(self.cookie_jar_path)

        except HTTPError:
            print("Your user appears to lack permissions to download data from the ASF Datapool.")
            print("New users: you must first log into Vertex and accept the EULA.")
            exit(-1)

        if resp_code in (300, 301, 302, 303):
            print("Redirect occurred, invalid cookie value!")
            return False

        return resp_code in (200, 307)

    def check_cookie_is_logged_in(self, cj):
        for cookie in cj:
            if cookie.name == 'urs_user_already_logged':
                return True
        return False

    def get_new_cookie(self):
        if not (self.username and self.password):
            print("Error: No credentials available")
            return False

        auth_cookie_url = self.asf_urs4['url'] + '?client_id=' + self.asf_urs4['client'] + '&redirect_uri=' + self.asf_urs4['redir'] + '&response_type=code&state='

        user_pass = base64.b64encode(bytes(f"{self.username}:{self.password}", "utf-8"))
        user_pass = user_pass.decode("utf-8")

        self.cookie_jar = MozillaCookieJar()
        opener = build_opener(HTTPCookieProcessor(self.cookie_jar), HTTPHandler(), HTTPSHandler(**self.context))
        request = Request(auth_cookie_url, headers={"Authorization": f"Basic {user_pass}"})

        try:
            response = opener.open(request)
            if self.check_cookie_is_logged_in(self.cookie_jar):
                self.cookie_jar.save(self.cookie_jar_path)
                return True
        except HTTPError as e:
            print(f"Login failed. Please check your credentials. Error: {str(e)}")
            return False

    def download_files(self, output_dir):
        """Download files with improved validation"""
        os.makedirs(output_dir, exist_ok=True)
        downloaded_files = []
        
        for url in self.files:
            try:
                file_name = os.path.basename(url)
                file_name = file_name.replace('.iso.xml', '.zip')
                output_path = os.path.join(output_dir, file_name)
                
                print(f"Attempting to download: {url}")
                print(f"Output path: {output_path}")
                
                opener = build_opener(
                    HTTPCookieProcessor(self.cookie_jar),
                    HTTPHandler(),
                    HTTPSHandler(**self.context)
                )
                
                download_url = url.replace('/METADATA_', '/').replace('.iso.xml', '.zip')
                request = Request(download_url)
                
                try:
                    response = opener.open(request, timeout=60)
                    
                    with open(output_path, 'wb') as f:
                        while True:
                            chunk = response.read(8192)
                            if not chunk:
                                break
                            f.write(chunk)
                    
                    print(f"Checking downloaded file: {output_path}")
                    if validate_slc_file(output_path):
                        print(f"Successfully validated: {file_name}")
                        downloaded_files.append(output_path)
                    else:
                        print(f"Validation failed: {file_name}")
                        if os.path.exists(output_path):
                            os.remove(output_path)
                            
                except Exception as e:
                    print(f"Error downloading {file_name}: {e}")
                    if os.path.exists(output_path):
                        os.remove(output_path)
                    continue
                    
            except Exception as e:
                print(f"Unexpected error for {url}: {e}")
                continue
        
        if not downloaded_files:
            raise RuntimeError("No valid files were downloaded")
        
        # Final validation step
        try:
            validated_files = validate_and_filter_download(downloaded_files)
            return validated_files
        except RuntimeError as e:
            print(f"Final validation failed: {str(e)}")
            return []