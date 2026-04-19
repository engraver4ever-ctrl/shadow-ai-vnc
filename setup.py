#!/usr/bin/env python3
from setuptools import setup, find_packages

setup(
    name="shadow-ai-vnc",
    version="0.1.0",
    description="Headless VNC client for AI agents with SSH tunneling and session persistence",
    author="Pantera",
    packages=find_packages(),
    install_requires=[
        "vncdotool>=1.2.0",
        "Pillow>=10.0.0",
        "paramiko>=3.0.0",
    ],
    entry_points={
        "console_scripts": [
            "shadow-ai-vnc=shadow_ai_vnc:main",
        ],
    },
    python_requires=">=3.8",
)
