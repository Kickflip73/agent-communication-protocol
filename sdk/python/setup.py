from setuptools import setup, find_packages

setup(
    name="acp-sdk",
    version="0.1.0",
    description="Agent Communication Protocol (ACP) SDK for Python",
    long_description=open("../../README.md").read(),
    long_description_content_type="text/markdown",
    author="ACP Community",
    url="https://github.com/Kickflip73/agent-communication-protocol",
    license="Apache 2.0",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "aiohttp>=3.9",
    ],
    extras_require={
        "dev": ["pytest", "pytest-asyncio"],
        "mqtt": ["aiomqtt>=2.0"],
        "fastapi": ["fastapi>=0.110", "uvicorn"],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries",
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
)
