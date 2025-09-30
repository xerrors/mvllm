#!/usr/bin/env python3
"""
Startup script for vLLM Router - legacy entrypoint
"""

import sys
import os

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Use the new CLI
from mvllm.cli import app

if __name__ == "__main__":
    app()