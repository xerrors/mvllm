"""
Load balancer for vLLM Router
"""

import random
import asyncio
from typing import List, Optional, Tuple
import logging
from .config import Config, ServerConfig, get_config

logger = logging.getLogger(__name__)

def get_load_balancer():
    """Get the global load balancer instance"""
    return LoadBalancer(get_config())

class LoadBalancer:
    def __init__(self, config: Config):
        self.config = config
    
    def get_server(self) -> Optional[ServerConfig]:
        """Get a server using weighted random selection"""
        healthy_servers = self.config.get_healthy_servers()
        
        if not healthy_servers:
            logger.warning("No healthy servers available")
            return None
        
        # Use weighted random selection
        servers_with_weight = self.config.get_servers_with_weight()
        
        if not servers_with_weight:
            return None
        
        # Calculate total weight
        total_weight = sum(weight for _, weight in servers_with_weight)
        
        # Generate random number and select server
        random_weight = random.randint(1, total_weight)
        
        current_weight = 0
        for server, weight in servers_with_weight:
            current_weight += weight
            if random_weight <= current_weight:
                logger.debug(f"Selected server: {server.url}")
                return server
        
        # Fallback to first server if something goes wrong
        return healthy_servers[0]
    
    def get_all_servers(self) -> List[ServerConfig]:
        """Get all servers (healthy and unhealthy)"""
        return self.config.servers
    
    def get_healthy_servers(self) -> List[ServerConfig]:
        """Get only healthy servers"""
        return self.config.get_healthy_servers()
    
    def get_server_stats(self) -> dict:
        """Get statistics about servers"""
        healthy_servers = self.get_healthy_servers()
        total_servers = len(self.config.servers)
        
        return {
            "total_servers": total_servers,
            "healthy_servers": len(healthy_servers),
            "unhealthy_servers": total_servers - len(healthy_servers),
            "servers": [
                {
                    "url": server.url,
                    "healthy": server.is_healthy,
                    "weight": server.weight,
                    "last_check": server.last_check.isoformat() if server.last_check else None
                }
                for server in self.config.servers
            ]
        }