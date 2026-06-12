"""Compatibility shim for legacy editable installs.

Package metadata lives in pyproject.toml. Keeping this file minimal prevents
setuptools from reporting duplicated metadata during modern builds.
"""

from setuptools import setup

setup()
