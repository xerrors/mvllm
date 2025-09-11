"""
Health checker for vLLM Router
"""

import asyncio
import httpx
from datetime import datetime
from typing import Dict, Optional
from loguru import logger
from .config import Config

class HealthChecker:
    def __init__(self, config: Config):
        self.config = config
        self.is_running = False
        self.task: Optional[asyncio.Task] = None
    
    async def start(self) -> None:
        """Start the health checker"""
        if self.is_running:
            logger.warning("Health checker is already running")
            return
        
        self.is_running = True
        self.task = asyncio.create_task(self._health_check_loop())
        logger.info("Health checker started")
    
    async def stop(self) -> None:
        """Stop the health checker"""
        if not self.is_running:
            return
        
        self.is_running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        
        logger.info("Health checker stopped")
    
    async def _health_check_loop(self) -> None:
        """Main health check loop"""
        while self.is_running:
            try:
                await self._check_all_servers()
                await asyncio.sleep(self.config.app_config.health_check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in health check loop: {e}")
                await asyncio.sleep(self.config.app_config.health_check_interval)
    
    async def _check_all_servers(self) -> None:
        """Check health of all servers"""
        tasks = []
        for server in self.config.servers:
            task = asyncio.create_task(self._check_server_health(server))
            tasks.append(task)
        
        # Wait for all health checks to complete
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _check_server_health(self, server) -> None:
        """Check health of a single server"""
        try:
            health_url = f"{server.url}/health"
            
            async with httpx.AsyncClient(
                timeout=self.config.app_config.health_check_timeout
            ) as client:
                response = await client.get(health_url)
                
                if response.status_code == 200:
                    was_healthy = server.is_healthy
                    self.config.update_server_health(server.url, True)
                    
                    if not was_healthy:
                        logger.info(f"Server {server.url} recovered")
                else:
                    self.config.update_server_health(server.url, False)
                    logger.warning(f"Server {server.url} health check failed: {response.status_code}")
        
        except httpx.TimeoutException:
            self.config.update_server_health(server.url, False)
            logger.warning(f"Server {server.url} health check timed out")
        
        except httpx.ConnectError:
            self.config.update_server_health(server.url, False)
            logger.warning(f"Failed to connect to server {server.url}")
        
        except Exception as e:
            self.config.update_server_health(server.url, False)
            logger.error(f"Error checking server {server.url} health: {e}")
    
    async def check_server_now(self, server_url: str) -> bool:
        """Check a specific server immediately"""
        server = self.config.get_server_by_url(server_url)
        if not server:
            return False
        
        try:
            health_url = f"{server.url}/health"
            
            async with httpx.AsyncClient(
                timeout=self.config.app_config.health_check_timeout
            ) as client:
                response = await client.get(health_url)
                
                is_healthy = response.status_code == 200
                self.config.update_server_health(server.url, is_healthy)
                
                return is_healthy
        
        except Exception as e:
            self.config.update_server_health(server.url, False)
            logger.error(f"Error checking server {server_url} health: {e}")
            return False