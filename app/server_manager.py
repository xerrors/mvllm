"""
Server manager for vLLM Router
"""

from typing import List
from loguru import logger
from .config import Config, ServerConfig, get_config
from .queue_manager import get_queue_manager

def get_server_manager():
    """Get the global ServerManager instance"""
    return ServerManager(get_config())

class ServerManager:
    def __init__(self, config: Config):
        self.config = config

    def get_all_servers(self) -> List[ServerConfig]:
        """Get all servers (healthy and unhealthy)"""
        return self.config.servers

    def get_healthy_servers(self) -> List[ServerConfig]:
        """Get only healthy servers"""
        return self.config.get_healthy_servers()

    def get_server_stats(self) -> dict:
        """Get statistics about servers"""
        # Note: queue_manager is fetched here to avoid circular dependency issues at startup
        queue_manager = get_queue_manager()
        healthy_servers = self.get_healthy_servers()
        total_servers = len(self.config.servers)
        queue_stats = queue_manager.get_queue_stats()

        return {
            "total_servers": total_servers,
            "healthy_servers": len(healthy_servers),
            "unhealthy_servers": total_servers - len(healthy_servers),
            "global_queue_size": queue_stats["global_queue_size"],
            "servers": [
                {
                    "url": server.url,
                    "healthy": server.is_healthy,
                    "queue_length": queue_stats["server_loads"].get(server.url, {}).get("current", 0),
                    "last_check": server.last_check.isoformat() if server.last_check else None
                }
                for server in self.config.servers
            ]
        }
