
"""
Common imports for the SAR processing pipeline.
"""

import os
import sys
import glob
import re
import json
import yaml
import base64
import subprocess
import requests
import rasterio
import urllib3
import asf_search as asf
import numpy as np
from math import floor, ceil
from bs4 import BeautifulSoup
from osgeo import gdal
from datetime import datetime, timedelta
from urllib.request import (
    build_opener, Request, HTTPCookieProcessor, HTTPHandler, 
    HTTPSHandler, urlopen, install_opener
)
from urllib.error import HTTPError
from http.cookiejar import MozillaCookieJar
import traceback
import time
import shutil
import getpass
import threading
import logging
import contextlib
from contextlib import redirect_stdout, redirect_stderr
from functools import wraps
import io
import argparse
import concurrent.futures
from functools import partial
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import xml.etree.ElementTree as ET
import tempfile
import zipfile
import fcntl

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Create convenience groupings for related imports
date_utils = {
    'datetime': datetime,
    'timedelta': timedelta
}

http_utils = {
    'build_opener': build_opener,
    'Request': Request,
    'HTTPCookieProcessor': HTTPCookieProcessor,
    'HTTPHandler': HTTPHandler,
    'HTTPSHandler': HTTPSHandler,
    'MozillaCookieJar': MozillaCookieJar
}

# Export all commonly used items
__all__ = [
    # Standard library
    'os', 'sys', 'glob', 're', 'json', 'traceback', 'time',
    'floor', 'ceil', 'datetime', 'timedelta',
    # Third-party
    'yaml', 'base64', 'subprocess', 'requests', 'rasterio',
    'urllib3', 'asf', 'np', 'BeautifulSoup', 'gdal',
    # Utility groupings
    'date_utils', 'http_utils'
]