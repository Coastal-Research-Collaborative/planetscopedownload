"""
Setup script for package

Joel Nicolow, Coastal Research Collaborative, March 2025
"""

from setuptools import setup, find_packages

setup(
    name="planetscopedownload",  # Package name (matches repo)
    version="0.1",
    packages=find_packages(),  # Automatically finds `geeutils/`
    install_requires=[
        "geojson",
        "requests",
    ],  # Add dependencies if needed
)