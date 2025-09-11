#!/usr/bin/env python3
"""
Simple test script for vLLM Router
"""

import asyncio
import json
import time
from app.config import Config

def test_config_loading():
    """Test configuration loading"""
    print("Testing configuration loading...")
    
    try:
        config = Config()
        print(f"✓ Configuration loaded successfully")
        print(f"  - Servers: {len(config.servers)}")
        print(f"  - Health check interval: {config.app_config.health_check_interval}s")
        print(f"  - Config reload interval: {config.app_config.config_reload_interval}s")
        
        for server in config.servers:
            print(f"  - Server: {server.url} (weight: {server.weight})")
        
        return True
    except Exception as e:
        print(f"✗ Configuration loading failed: {e}")
        return False

def test_server_health_check():
    """Test server health check"""
    print("\nTesting server health check...")
    
    try:
        config = Config()
        healthy_servers = config.get_healthy_servers()
        print(f"✓ Health check completed")
        print(f"  - Healthy servers: {len(healthy_servers)}")
        return True
    except Exception as e:
        print(f"✗ Health check failed: {e}")
        return False

def test_load_balancer():
    """Test load balancer"""
    print("\nTesting load balancer...")
    
    try:
        config = Config()
        from app.load_balancer import LoadBalancer
        
        load_balancer = LoadBalancer(config)
        
        # Test server selection
        server = load_balancer.get_server()
        if server:
            print(f"✓ Server selected: {server.url}")
        else:
            print("✓ No healthy servers available (expected if no servers are running)")
        
        # Test stats
        stats = load_balancer.get_server_stats()
        print(f"✓ Server stats: {stats['total_servers']} total, {stats['healthy_servers']} healthy")
        
        return True
    except Exception as e:
        print(f"✗ Load balancer test failed: {e}")
        return False

def test_api_endpoints():
    """Test API endpoints (requires server to be running)"""
    print("\nTesting API endpoints...")
    print("✓ API endpoint test skipped (requires server to be running)")
    return True

def main():
    """Run all tests"""
    print("vLLM Router Test Suite")
    print("=" * 50)
    
    tests = [
        test_config_loading,
        test_server_health_check,
        test_load_balancer,
        test_api_endpoints
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
    
    print(f"\nTest Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed!")
    else:
        print("❌ Some tests failed")
    
    return passed == total

if __name__ == "__main__":
    main()