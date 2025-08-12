"""
Setup script for SAR Data Processing Pipeline
"""

from setuptools import setup, find_packages
import os

# Read the README file
with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

# Read the requirements file
with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [line.strip() for line in fh if line.strip() and not line.startswith("#")]

# Read version
exec(open("version.py").read())

setup(
    name="sentinel-sar-processing",
    version=__version__,
    author=__author__,
    author_email=__email__,
    description=__description__,
    long_description=long_description,
    long_description_content_type="text/markdown",
    url=__url__,
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Science/Research",
        "Topic :: Scientific/Engineering :: GIS",
        "Topic :: Scientific/Engineering :: Image Processing",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.8",
    install_requires=requirements,
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-cov>=4.0.0",
            "black>=22.0.0",
            "flake8>=5.0.0",
        ],
        "docs": [
            "sphinx>=5.0.0",
            "sphinx-rtd-theme>=1.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "sar-process=main:main",
        ],
    },
    keywords="SAR, Sentinel-1, MAXAR, RTC, disaster-response, remote-sensing",
    project_urls={
        "Bug Reports": "https://github.com/venkateshkolluru95/Sentinel-SAR-data-processing-package/issues",
        "Source": "https://github.com/venkateshkolluru95/Sentinel-SAR-data-processing-package",
        "Documentation": "https://github.com/venkateshkolluru95/Sentinel-SAR-data-processing-package#readme",
    },
    include_package_data=True,
    zip_safe=False,
)
