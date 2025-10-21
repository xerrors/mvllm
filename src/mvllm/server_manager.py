"""
Server manager for vLLM Router
"""

from .config import Config, ServerConfig, get_config
from .load_manager import get_load_manager


def get_server_manager():
    """Get the global ServerManager instance"""
    return ServerManager(get_config())


class ServerManager:
    def __init__(self, config: Config):
        self.config = config

    def get_all_servers(self) -> list[ServerConfig]:
        """Get all servers (healthy and unhealthy)"""
        return self.config.servers

    def get_healthy_servers(self) -> list[ServerConfig]:
        """Get only healthy servers"""
        return self.config.get_healthy_servers()

    def get_server_stats(self) -> dict:
        """Get statistics about servers"""
        # Note: load_manager is fetched here to avoid circular dependency issues at startup
        load_manager = get_load_manager()
        healthy_servers = self.get_healthy_servers()
        total_servers = len(self.config.servers)
        load_stats = load_manager.get_load_stats()

        return {
            "total_servers": total_servers,
            "healthy_servers": len(healthy_servers),
            "unhealthy_servers": total_servers - len(healthy_servers),
            "total_active_load": load_stats["summary"]["total_active_load"],
            "servers": [
                {
                    "url": server.url,
                    "healthy": server.is_healthy,
                    "current_load": load_stats["server_loads"]
                    .get(server.url, {})
                    .get("current_load", 0),
                    "utilization": load_stats["server_loads"]
                    .get(server.url, {})
                    .get("utilization", 0),
                    "last_check": server.last_check.isoformat()
                    if server.last_check
                    else None,
                    "supported_models": server.supported_models,
                    "models_last_updated": server.models_last_updated.isoformat()
                    if server.models_last_updated
                    else None,
                }
                for server in self.config.servers
            ],
        }
