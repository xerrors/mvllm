"""
Configuration reloader for vLLM Router
"""

import asyncio
import logging
from typing import Optional
from .config import Config

logger = logging.getLogger(__name__)

class ConfigReloader:
    def __init__(self, config: Config):
        self.config = config
        self.is_running = False
        self.task: Optional[asyncio.Task] = None
    
    async def start(self) -> None:
        """Start the config reloader"""
        if self.is_running:
            logger.warning("Config reloader is already running")
            return
        
        self.is_running = True
        self.task = asyncio.create_task(self._config_reload_loop())
        logger.info("Config reloader started")
    
    async def stop(self) -> None:
        """Stop the config reloader"""
        if not self.is_running:
            return
        
        self.is_running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        
        logger.info("Config reloader stopped")
    
    async def _config_reload_loop(self) -> None:
        """Main config reload loop"""
        while self.is_running:
            try:
                # Check if config needs to be reloaded
                if self.config.reload_if_needed():
                    logger.info("Configuration reloaded successfully")
                
                await asyncio.sleep(self.config.app_config.config_reload_interval)
            
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in config reload loop: {e}")
                await asyncio.sleep(self.config.app_config.config_reload_interval)
    
    async def reload_now(self) -> bool:
        """Reload configuration immediately"""
        try:
            logger.info("Manual configuration reload triggered")
            return self.config.reload_if_needed()
        except Exception as e:
            logger.error(f"Error during manual config reload: {e}")
            return False