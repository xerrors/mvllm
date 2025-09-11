"""
Configuration management for vLLM Router
"""

import os
import toml
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, validator
from datetime import datetime
from loguru import logger

# Global configuration instance
_config_instance = None
_config_lock = None

def get_config() -> 'Config':
    """Get the global configuration instance"""
    global _config_instance
    if _config_instance is None:
        _config_instance = Config()
    return _config_instance

def reset_config():
    """Reset the global configuration instance (for testing)"""
    global _config_instance
    _config_instance = None

class ServerConfig(BaseModel):
    url: str
    weight: int = Field(default=1, ge=1, le=100)
    is_healthy: bool = Field(default=True)
    last_check: Optional[datetime] = Field(default=None)
    
    @validator('url')
    def validate_url(cls, v):
        if not v.startswith(('http://', 'https://')):
            raise ValueError('URL must start with http:// or https://')
        return v

class AppConfig(BaseModel):
    health_check_interval: int = Field(default=30, ge=1)
    config_reload_interval: int = Field(default=60, ge=1)
    request_timeout: int = Field(default=30, ge=1)
    health_check_timeout: int = Field(default=5, ge=1)
    max_retries: int = Field(default=3, ge=0)

class Config:
    def __init__(self, config_path: str = "servers.toml"):
        self.config_path = config_path
        self.servers: List[ServerConfig] = []
        self.app_config: AppConfig = AppConfig()
        self.last_modified: Optional[datetime] = None
        self.load_config()
    
    def load_config(self) -> None:
        """Load configuration from TOML file"""
        try:
            if not os.path.exists(self.config_path):
                logger.warning(f"Config file {self.config_path} not found, using defaults")
                return
            
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config_data = toml.load(f)
            
            # Load server configurations
            servers_data = config_data.get('servers', {}).get('servers', [])
            self.servers = [ServerConfig(**server_data) for server_data in servers_data]
            
            # Load app configuration
            app_config_data = config_data.get('config', {})
            self.app_config = AppConfig(**app_config_data)
            
            self.last_modified = datetime.fromtimestamp(os.path.getmtime(self.config_path))
            logger.info(f"Configuration loaded from {self.config_path}")
            logger.info(f"Loaded {len(self.servers)} servers")
            
        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            raise
    
    def reload_if_needed(self) -> bool:
        """Reload configuration if file has been modified"""
        try:
            if not os.path.exists(self.config_path):
                return False
            
            current_mtime = datetime.fromtimestamp(os.path.getmtime(self.config_path))
            
            if self.last_modified is None or current_mtime > self.last_modified:
                logger.info("Configuration file modified, reloading...")
                self.load_config()
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to check configuration file modification: {e}")
            return False
    
    def get_healthy_servers(self) -> List[ServerConfig]:
        """Get list of healthy servers"""
        return [server for server in self.servers if server.is_healthy]
    
    def get_server_by_url(self, url: str) -> Optional[ServerConfig]:
        """Get server configuration by URL"""
        for server in self.servers:
            if server.url == url:
                return server
        return None
    
    def update_server_health(self, url: str, is_healthy: bool) -> None:
        """Update server health status"""
        server = self.get_server_by_url(url)
        if server:
            server.is_healthy = is_healthy
            server.last_check = datetime.now()
            logger.info(f"Server {url} health status updated to: {is_healthy}")
    
    def get_total_weight(self) -> int:
        """Get total weight of all servers"""
        return sum(server.weight for server in self.servers)
    
    def get_servers_with_weight(self) -> List[tuple]:
        """Get list of (server, weight) tuples for weighted selection"""
        return [(server, server.weight) for server in self.servers if server.is_healthy]