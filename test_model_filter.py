#!/usr/bin/env python3
"""
Test script for model filter functionality
"""

import os
import sys
import asyncio
from src.mvllm.config import get_config
from src.mvllm.load_manager import get_load_manager

async def test_model_filter():
    """Test the model filter functionality"""
    
    # Set up environment
    os.environ["CONFIG_PATH"] = "servers.toml"
    os.environ["LOG_TO_CONSOLE"] = "true"
    
    # Test without model filter
    print("=== Testing without model filter ===")
    config = get_config()
    load_manager = get_load_manager(fullscreen_mode=False, model_filter=None)
    
    # Create a test panel
    panel = load_manager.create_load_status_panel()
    print("Panel created successfully without model filter")
    
    # Test with model filter
    print("\n=== Testing with model filter ===")
    load_manager_with_filter = get_load_manager(fullscreen_mode=False, model_filter="llama-7b")
    
    # Create a test panel with filter
    panel_with_filter = load_manager_with_filter.create_load_status_panel()
    print("Panel created successfully with model filter")
    
    print("\n=== Test completed ===")

if __name__ == "__main__":
    asyncio.run(test_model_filter())
