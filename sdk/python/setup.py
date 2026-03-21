"""
Legacy setup.py — kept for editable installs with older pip versions.
The canonical packaging config is in pyproject.toml at the repo root.

For SDK-only install (RelayClient, AsyncRelayClient):
    pip install ./sdk/python

For the full relay (acp_relay.py + SDK + CLI entry-point):
    pip install .   (from repo root)
"""
from setuptools import setup, find_packages

setup(
    name="acp-relay-sdk",
    version="0.9.0.dev0",
    description="ACP Python SDK — RelayClient & AsyncRelayClient for acp_relay.py",
    long_description=open("../../README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    author="ACP Community",
    url="https://github.com/Kickflip73/agent-communication-protocol",
    license="Apache-2.0",
    packages=find_packages(exclude=["tests*"]),
    python_requires=">=3.10",
    # SDK itself is stdlib-only — zero required dependencies
    install_requires=[],
    extras_require={
        "dev": ["pytest>=7.4", "pytest-asyncio>=0.23"],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries",
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
    ],
)
