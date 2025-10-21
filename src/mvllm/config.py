"""
Configuration management for vLLM Router
"""

import os
import toml
import httpx
from typing import List, Optional, Dict, Tuple
from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from loguru import logger

__all__ = [
    "Config",
    "ServerConfig",
    "AppConfig",
    "HealthCheckStats",
    "get_config",
    "reset_config",
]

# Global configuration instance
_config_instance = None
_config_lock = None


def get_config() -> "Config":
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
    is_healthy: bool = Field(default=True)
    last_check: Optional[datetime] = Field(default=None)
    consecutive_failures: int = Field(default=0)
    last_failure_time: Optional[datetime] = Field(default=None)
    max_concurrent_requests: int = Field(
        default=3, ge=1
    )  # Maximum concurrent requests for this server

    # Active health check related fields
    health_stats: "HealthCheckStats" = Field(default_factory=lambda: HealthCheckStats())

    # Model information
    supported_models: List[str] = Field(
        default_factory=list
    )  # List of models supported by this server
    models_last_updated: Optional[datetime] = Field(
        default=None
    )  # Last time model info was updated

    @field_validator("url")
    @classmethod
    def validate_url(cls, v):
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        return v


class HealthCheckStats(BaseModel):
    """Model to store health check statistics for a server."""

    response_times: List[float] = Field(default_factory=list)
    success_rate: float = 1.0
    total_checks: int = 0
    successful_checks: int = 0
    avg_response_time: float = 0.0
    last_response_time: Optional[float] = None


class AppConfig(BaseModel):
    health_check_interval: int = Field(default=30, ge=1)
    config_reload_interval: int = Field(default=60, ge=1)
    request_timeout: int = Field(default=30, ge=1)
    health_check_timeout: int = Field(default=5, ge=1)
    max_retries: int = Field(default=3, ge=0)
    failure_threshold: int = Field(default=2, ge=1)
    auto_recovery_threshold: int = Field(default=60, ge=1)

    # Active health check configuration
    enable_active_health_check: bool = Field(
        default=True
    )  # Whether to enable active health checks
    health_check_max_response_time: float = Field(
        default=10.0, ge=0.1
    )  # Maximum acceptable response time (seconds)
    health_check_min_success_rate: float = Field(
        default=0.8, ge=0.0, le=1.0
    )  # Minimum success rate
    health_check_window_size: int = Field(
        default=10, ge=1
    )  # Health check statistics window size
    health_check_consecutive_failures: int = Field(
        default=3, ge=1
    )  # Consecutive failures before marking unhealthy


class Config:
    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = os.getenv("CONFIG_PATH", "servers.toml")
        self.config_path = config_path
        self.servers: List[ServerConfig] = []
        self.app_config: AppConfig = AppConfig()
        self.last_modified: Optional[datetime] = None
        self.load_config()

    def load_config(self) -> None:
        """Load configuration from TOML file"""
        try:
            if not os.path.exists(self.config_path):
                logger.warning(
                    f"Config file {self.config_path} not found, using defaults"
                )
                return

            with open(self.config_path, "r", encoding="utf-8") as f:
                config_data = toml.load(f)

            # Load server configurations
            servers_data = config_data.get("servers", {}).get("servers", [])
            self.servers = [ServerConfig(**server_data) for server_data in servers_data]

            # Load app configuration
            app_config_data = config_data.get("config", {})
            self.app_config = AppConfig(**app_config_data)

            self.last_modified = datetime.fromtimestamp(
                os.path.getmtime(self.config_path)
            )
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
            now = datetime.now()
            server.last_check = now

            if is_healthy:
                # Server is healthy - reset failure count
                server.consecutive_failures = 0
                server.last_failure_time = None
                # Only mark as healthy if it wasn't already healthy
                if not server.is_healthy:
                    server.is_healthy = True
                    logger.info(
                        f"Server {url} recovered (health status: {server.is_healthy})"
                    )
            else:
                # Server failed - increment failure count
                server.consecutive_failures += 1
                server.last_failure_time = now

                # Only mark as unhealthy after multiple consecutive failures
                failure_threshold = self.app_config.failure_threshold
                if server.consecutive_failures >= failure_threshold:
                    if server.is_healthy:  # Only log if status actually changed
                        server.is_healthy = False
                        logger.warning(
                            f"Server {url} marked as unhealthy after {server.consecutive_failures} consecutive failures"
                        )
                else:
                    logger.info(
                        f"Server {url} failure #{server.consecutive_failures}/{failure_threshold}"
                    )

    def auto_recover_servers(self) -> None:
        """Auto-recover servers that haven't failed recently"""
        now = datetime.now()
        recovery_threshold = self.app_config.auto_recovery_threshold

        for server in self.servers:
            if not server.is_healthy:
                # If server has been marked unhealthy but hasn't failed recently, try to recover it
                if (
                    server.last_failure_time is None
                    or (now - server.last_failure_time).total_seconds()
                    > recovery_threshold
                ):
                    # Reset failure count but don't mark as healthy immediately
                    # The next active health check will determine if it's actually healthy
                    server.consecutive_failures = 0
                    logger.info(
                        f"Server {server.url} reset for auto-recovery attempt (no recent failures in {recovery_threshold}s)"
                    )
                    logger.info(
                        f"Server {server.url} will be re-evaluated in next health check cycle"
                    )

                    # If active health check is disabled, mark as healthy for immediate recovery
                    if not self.app_config.enable_active_health_check:
                        server.is_healthy = True
                        logger.info(
                            f"Server {server.url} auto-recovered (active health check disabled)"
                        )
                    else:
                        # Active health check will evaluate the server in the next cycle
                        logger.info(
                            f"Server {server.url} will be tested in next active health check"
                        )

    async def check_server_health(self, server: ServerConfig) -> Tuple[bool, float]:
        """Check the health of a single server"""
        import time

        start_time = time.time()

        try:
            # Use a simple health check endpoint - try to access /health or /v1/models
            health_urls = ["/health", "/v1/models"]

            async with httpx.AsyncClient(
                timeout=self.app_config.health_check_timeout
            ) as client:
                for health_url in health_urls:
                    try:
                        response = await client.get(f"{server.url}{health_url}")
                        response.raise_for_status()
                        response_time = time.time() - start_time
                        await self.update_server_health_stats(
                            server, True, response_time
                        )
                        return True, response_time
                    except (
                        httpx.TimeoutException,
                        httpx.ConnectError,
                        httpx.HTTPStatusError,
                    ):
                        continue  # Try next health check URL

            # If we get here, all health check URLs failed
            response_time = time.time() - start_time
            await self.update_server_health_stats(server, False, response_time)
            return False, response_time

        except Exception as e:
            logger.error(f"Error checking server {server.url}: {e}")
            response_time = time.time() - start_time
            await self.update_server_health_stats(server, False, response_time)
            return False, response_time

    async def update_server_health_stats(
        self, server: ServerConfig, success: bool, response_time: float
    ):
        """Update server statistics and health status after a health check."""
        now = datetime.now()
        server.last_check = now
        stats = server.health_stats
        stats.last_response_time = response_time

        # Update response times list
        stats.response_times.append(response_time)
        if len(stats.response_times) > self.app_config.health_check_window_size:
            stats.response_times.pop(0)

        # Update success/failure statistics
        stats.total_checks += 1
        if success:
            stats.successful_checks += 1
            server.consecutive_failures = 0
        else:
            server.consecutive_failures += 1
            server.last_failure_time = now

        # Calculate success rate and average response time
        if stats.total_checks > 0:
            stats.success_rate = stats.successful_checks / stats.total_checks

        if stats.response_times:
            stats.avg_response_time = sum(stats.response_times) / len(
                stats.response_times
            )

        # Update overall health status if active health check is enabled
        if not self.app_config.enable_active_health_check:
            return

        was_healthy = server.is_healthy

        success_rate_ok = (
            stats.success_rate >= self.app_config.health_check_min_success_rate
        )
        response_time_ok = (
            stats.avg_response_time <= self.app_config.health_check_max_response_time
        )
        consecutive_failures_ok = (
            server.consecutive_failures
            < self.app_config.health_check_consecutive_failures
        )

        new_health_status = (
            success_rate_ok and response_time_ok and consecutive_failures_ok
        )

        if new_health_status != was_healthy:
            server.is_healthy = new_health_status
            if new_health_status:
                logger.info(
                    f"Server {server.url} recovered - success_rate: {stats.success_rate:.2f}, "
                    f"avg_response_time: {stats.avg_response_time:.2f}s, consecutive_failures: {server.consecutive_failures}"
                )
            else:
                logger.warning(
                    f"Server {server.url} marked as unhealthy - success_rate: {stats.success_rate:.2f}, "
                    f"avg_response_time: {stats.avg_response_time:.2f}s, consecutive_failures: {server.consecutive_failures}"
                )

    async def perform_health_checks(self) -> Dict[str, Tuple[bool, float]]:
        """Perform health checks on all servers"""
        if not self.app_config.enable_active_health_check:
            return {}

        logger.debug("Starting health checks for all servers")
        results = {}

        for server in self.servers:
            is_healthy, response_time = await self.check_server_health(server)
            results[server.url] = (is_healthy, response_time)
            logger.debug(
                f"Health check for {server.url}: healthy={is_healthy}, response_time={response_time:.2f}s"
            )

        logger.info(f"Completed health checks: {len(results)} servers checked")
        return results

    async def fetch_server_models(self, server: ServerConfig) -> None:
        """Fetch supported models from a vLLM server"""
        try:
            async with httpx.AsyncClient(
                timeout=self.app_config.health_check_timeout
            ) as client:
                response = await client.get(f"{server.url}/v1/models")
                response.raise_for_status()

                models_data = response.json()
                models = []

                # vLLM's /v1/models API typically returns {"object": "list", "data": [{"id": "model_name", ...}, ...]}
                if "data" in models_data:
                    for model_info in models_data["data"]:
                        if "id" in model_info:
                            models.append(model_info["id"])

                server.supported_models = models
                server.models_last_updated = datetime.now()
                logger.info(
                    f"Updated models for {server.url}: {len(models)} models - {models}"
                )

        except Exception as e:
            logger.warning(f"Failed to fetch models from {server.url}: {e}")
            # Don't update model information if fetch failed

    async def update_all_server_models(self) -> None:
        """Update model information for all servers"""
        logger.info("Updating model information for all servers...")

        for server in self.servers:
            await self.fetch_server_models(server)

        logger.info("Model information update completed")

    def get_servers_supporting_model(self, model_name: str) -> List[ServerConfig]:
        """Get list of servers that support the specified model"""
        return [
            server for server in self.servers if model_name in server.supported_models
        ]

    def get_healthy_servers_supporting_model(
        self, model_name: str
    ) -> List[ServerConfig]:
        """Get list of healthy servers that support the specified model"""
        return [
            server
            for server in self.get_servers_supporting_model(model_name)
            if server.is_healthy
        ]
