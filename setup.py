# -*- coding: utf-8 -*-
from setuptools import setup, find_packages
import os
import re

with open("requirements.txt") as f:
    install_requires = f.read().strip().split("\n")

# Get version from __version__ variable in posawesome/__init__.py without importing the module
def get_version():
    version_file = os.path.join(os.path.dirname(__file__), 'posawesome', '__init__.py')
    with open(version_file) as f:
        content = f.read()
        match = re.search(r"__version__\s*=\s*['\"]([^'\"]*)['\"]", content)
        if match:
            return match.group(1)
    raise RuntimeError("Unable to find version string.")

version = get_version()

setup(
    name="posawesome",
    version=version,
    description="POS Awesome",
    author="Yousef Restom",
    author_email="youssef@totrox.com",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=install_requires,
)
