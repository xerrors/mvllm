"""
Real-time load management for vLLM Router
"""

import asyncio
import aiohttp
import sys
from datetime import datetime
from typing import Optional
from loguru import logger
from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.panel import Panel
from .config import Config, get_config

__all__ = [
    "LoadManager",
    "get_load_manager",
]


class LoadManager:
    def __init__(
        self, config: Config, fullscreen_mode: bool = False, show_models: bool = False
    ):
        self.config = config
        self.server_loads: dict[str, dict] = {}  # Server load metrics dictionary
        self.last_updated: dict[str, datetime] = {}  # Last update time
        self.load_check_lock = asyncio.Lock()
        self.fullscreen_mode = fullscreen_mode
        self.show_models = show_models  # Whether to display model information

        # Rich console for status display
        if fullscreen_mode:
            # Fullscreen mode uses stderr to avoid conflicts with log output
            self.console = Console(file=sys.stderr, width=None, height=None)
        else:
            # Normal mode uses stdout
            self.console = Console(file=sys.stdout)

        self.live_display = None

        # Initialize server status
        self._initialize_servers()

    def _initialize_servers(self):
        """Initialize all server status"""
        for server in self.config.servers:
            self.server_loads[server.url] = {
                "num_requests_running": 0,
                "num_requests_waiting": 0,
                "gpu_cache_usage_perc": 0.0,
                "process_max_fds": 65535,
                "system_load": 0,
            }
            # Server status now uniformly uses the is_healthy field in config
            self.last_updated[server.url] = datetime.now()

    async def get_server_load(self, server_url: str) -> Optional[dict]:
        """Get real-time load of the specified server (using /metrics endpoint)"""
        try:
            # Use the /metrics endpoint provided by the server to get actual load
            metrics_url = f"{server_url}/metrics"

            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=5)
            ) as session:
                async with session.get(metrics_url) as response:
                    if response.status == 200:
                        metrics_text = await response.text()
                        load_metrics = self._parse_vllm_metrics(metrics_text)
                        logger.debug(
                            f"Got load metrics from {server_url}: {load_metrics['system_load']}"
                        )
                        return load_metrics
                    else:
                        logger.warning(
                            f"Failed to get metrics from {server_url}, status: {response.status}"
                        )
                        return None
        except Exception as e:
            logger.error(f"Error getting load from {server_url}: {e}")
            return None

    def _parse_vllm_metrics(self, metrics_text: str) -> dict:
        """Parse vLLM metrics data and extract multiple metrics"""
        try:
            metrics = {
                "num_requests_running": 0,
                "num_requests_waiting": 0,
                "gpu_cache_usage_perc": 0.0,
                "process_max_fds": 65535,  # Default value
                "system_load": 0,  # Calculated composite load
            }

            for line in metrics_text.split("\n"):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                # Parse different metrics
                if line.startswith("vllm:num_requests_running"):
                    value = self._extract_metric_value(line)
                    if value is not None:
                        metrics["num_requests_running"] = int(value)

                elif line.startswith("vllm:num_requests_waiting"):
                    value = self._extract_metric_value(line)
                    if value is not None:
                        metrics["num_requests_waiting"] = int(value)

                elif line.startswith("vllm:gpu_cache_usage_perc"):
                    value = self._extract_metric_value(line)
                    if value is not None:
                        metrics["gpu_cache_usage_perc"] = float(value)

                elif line.startswith("process_max_fds"):
                    value = self._extract_metric_value(line)
                    if value is not None:
                        metrics["process_max_fds"] = int(value)

            # Calculate composite load: running + waiting, but not exceeding max file descriptor limit
            total_requests = (
                metrics["num_requests_running"] + metrics["num_requests_waiting"]
            )
            # Adjust load weight based on system file descriptor limit
            max_concurrent_by_fds = max(
                1, metrics["process_max_fds"] // 1000
            )  # Estimate max concurrent requests
            metrics["system_load"] = min(total_requests, max_concurrent_by_fds)

            logger.debug(
                f"Parsed metrics: running={metrics['num_requests_running']}, "
                f"waiting={metrics['num_requests_waiting']}, "
                f"gpu_cache={metrics['gpu_cache_usage_perc']:.1f}%, "
                f"max_fds={metrics['process_max_fds']}, "
                f"system_load={metrics['system_load']}"
            )

            return metrics

        except Exception as e:
            logger.error(f"Error parsing vLLM metrics: {e}")
            return {
                "num_requests_running": 0,
                "num_requests_waiting": 0,
                "gpu_cache_usage_perc": 0.0,
                "process_max_fds": 65535,
                "system_load": 0,
            }

    def _extract_metric_value(self, line: str) -> float:
        """Extract numeric value from metrics line"""
        try:
            # Parse lines like: vllm:num_requests_running{engine="0",model_name="llama3.1:8b"} 15.0
            parts = line.split(" ")
            if len(parts) >= 2:
                return float(parts[-1])
        except (ValueError, IndexError):
            pass
        return None

    async def update_all_server_loads(self):
        """Update load information for all servers"""
        async with self.load_check_lock:
            tasks = []
            for server in self.config.servers:
                if server.is_healthy:  # Only check healthy servers
                    tasks.append(self._update_single_server_load(server.url))

            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

    async def _update_single_server_load(self, server_url: str):
        """Update load for a single server"""
        try:
            load = await self.get_server_load(server_url)
            if load is not None:
                self.server_loads[server_url] = load
                self.last_updated[server_url] = datetime.now()
            else:
                logger.warning(f"Failed to get metrics from {server_url}")
        except Exception as e:
            logger.error(f"Error updating load for {server_url}: {e}")

    def get_load_stats(self) -> dict:
        """Get load statistics"""
        healthy_servers = self.config.get_healthy_servers()

        return {
            "total_servers": len(self.config.servers),
            "healthy_servers": len(healthy_servers),
            "server_loads": {
                server.url: {
                    "current_load": self.server_loads.get(server.url, {}).get(
                        "system_load", 0
                    ),
                    "max_capacity": server.max_concurrent_requests,
                    "available_capacity": max(
                        0,
                        server.max_concurrent_requests
                        - self.server_loads.get(server.url, {}).get("system_load", 0),
                    ),
                    "utilization": min(
                        100,
                        (
                            self.server_loads.get(server.url, {}).get("system_load", 0)
                            / server.max_concurrent_requests
                            * 100
                        ),
                    )
                    if server.max_concurrent_requests > 0
                    else 0,
                    "status": server.is_healthy,
                    "last_updated": self.last_updated.get(server.url, None).isoformat()
                    if self.last_updated.get(server.url, None)
                    else None,
                    "detailed_metrics": {
                        "num_requests_running": self.server_loads.get(
                            server.url, {}
                        ).get("num_requests_running", 0),
                        "num_requests_waiting": self.server_loads.get(
                            server.url, {}
                        ).get("num_requests_waiting", 0),
                        "gpu_cache_usage_perc": self.server_loads.get(
                            server.url, {}
                        ).get("gpu_cache_usage_perc", 0.0),
                        "process_max_fds": self.server_loads.get(server.url, {}).get(
                            "process_max_fds", 65535
                        ),
                    },
                }
                for server in self.config.servers
            },
            "summary": {
                "total_active_load": sum(
                    metrics.get("system_load", 0)
                    for metrics in self.server_loads.values()
                ),
                "total_capacity": sum(
                    server.max_concurrent_requests for server in self.config.servers
                ),
                "overall_utilization": sum(
                    metrics.get("system_load", 0)
                    for metrics in self.server_loads.values()
                )
                / sum(server.max_concurrent_requests for server in self.config.servers)
                * 100
                if sum(server.max_concurrent_requests for server in self.config.servers)
                > 0
                else 0,
            },
        }

    def create_load_status_panel(self):
        """Create load status panel"""
        try:
            stats = self.get_load_stats()

            # Create main table - display detailed load data (use index instead of time, time shown in title)
            table = Table(show_header=True, header_style="bold blue", box=None)
            table.add_column("#", style="cyan", justify="right", width=2)
            table.add_column(
                "Server", style="green", width=25
            )  # Reserve enough space for full URL

            # Only display model column when model parameter is specified
            if self.show_models:
                table.add_column(
                    "Models", style="blue", width=20
                )  # New model name column

            table.add_column("Running", style="yellow", justify="right", width=8)
            table.add_column("Waiting", style="bright_yellow", justify="right", width=8)
            table.add_column("Capacity", style="magenta", justify="right", width=8)
            table.add_column("Usage", style="cyan", justify="right", width=7)

            # Server load information
            server_rows = []
            current_time = datetime.now().strftime("%H:%M:%S")
            row_index = 1

            for server in self.config.servers:
                server_name = server.url  # Display full server_url
                load_info = stats["server_loads"][server.url]
                max_capacity = load_info["max_capacity"]
                utilization = load_info["utilization"]

                # Get server health status - uniformly use status from config
                server_config = self.config.get_server_by_url(server.url)
                status = server_config.is_healthy if server_config else False

                # Get detailed metrics
                detailed_metrics = load_info["detailed_metrics"]
                running = detailed_metrics["num_requests_running"]
                waiting = detailed_metrics["num_requests_waiting"]

                # Format model name display
                if server.supported_models:
                    # Display first few models, if too many then show count
                    if len(server.supported_models) <= 3:
                        models_display = ", ".join(server.supported_models)
                    else:
                        models_display = f"{', '.join(server.supported_models[:2])} (+{len(server.supported_models) - 2})"
                else:
                    models_display = "[dim]No models[/dim]"

                # Set color based on load status
                if not status:
                    # Add strikethrough for unhealthy servers
                    server_name = f"[red strike]{server_name}[/red strike]"
                    models_display = f"[red strike]{models_display}[/red strike]"
                    running_str = f"[red]{running}[/red]"
                    waiting_str = f"[red]{waiting}[/red]"
                    utilization_str = f"[red]{utilization:.1f}%[/red]"
                elif utilization >= 90:
                    server_name = f"[red]{server_name}[/red]"
                    running_str = f"[red]{running}[/red]"
                    waiting_str = f"[red]{waiting}[/red]"
                    utilization_str = f"[red]{utilization:.1f}%[/red]"
                elif utilization >= 70:
                    server_name = f"[yellow]{server_name}[/yellow]"
                    running_str = f"[bright_yellow]{running}[/bright_yellow]"
                    waiting_str = f"[bright_yellow]{waiting}[/bright_yellow]"
                    utilization_str = f"[yellow]{utilization:.1f}%[/yellow]"
                else:
                    server_name = f"[green]{server_name}[/green]"
                    running_str = f"[green]{running}[/green]"
                    waiting_str = f"[green]{waiting}[/green]"
                    utilization_str = f"[green]{utilization:.1f}%[/green]"

                # Build row data based on whether to display model column
                if self.show_models:
                    server_rows.append(
                        (
                            f"{row_index}",
                            server_name,
                            models_display,
                            running_str,
                            waiting_str,
                            f"{max_capacity}",
                            utilization_str,
                        )
                    )
                else:
                    server_rows.append(
                        (
                            f"{row_index}",
                            server_name,
                            running_str,
                            waiting_str,
                            f"{max_capacity}",
                            utilization_str,
                        )
                    )
                row_index += 1

            # Add server rows
            for row in server_rows:
                table.add_row(*row)

            # Calculate overall status
            overall_utilization = stats["summary"]["overall_utilization"]
            healthy_count = stats["healthy_servers"]
            total_servers = stats["total_servers"]

            # Calculate total running and waiting counts
            total_running = sum(
                load_info["detailed_metrics"]["num_requests_running"]
                for load_info in stats["server_loads"].values()
            )
            total_waiting = sum(
                load_info["detailed_metrics"]["num_requests_waiting"]
                for load_info in stats["server_loads"].values()
            )

            if total_servers == 0:
                health_status = "No servers"
            elif healthy_count == total_servers:
                health_status = "All healthy"
            elif healthy_count >= total_servers * 0.7:
                health_status = "Partially healthy"
            else:
                health_status = "Mostly unhealthy"

            # Choose different panel style based on mode
            displayed_servers = len(server_rows)

            if self.fullscreen_mode:
                # Fullscreen mode: more concise title and style
                panel_title = f"vLLM Router Monitor ({current_time})"
                panel_subtitle = f"{displayed_servers}/{total_servers} Servers | {total_running} Running | {total_waiting} Waiting | {overall_utilization:.1f}% Usage"
                border_style = "bright_blue"
            else:
                # Normal mode: original detailed style
                panel_title = f"vLLM Router - Real-time Load Monitor ({current_time})"
                panel_subtitle = f"Health: {healthy_count}/{total_servers} | {health_status} | Running: {total_running} | Waiting: {total_waiting} | Total Usage: {overall_utilization:.1f}%"
                border_style = "blue"

            # Create main panel
            panel = Panel(
                table,
                title=panel_title,
                subtitle=panel_subtitle,
                border_style=border_style,
                padding=(0, 1),  # Reduce padding in fullscreen mode
            )

            return panel

        except Exception as e:
            # If table creation fails, return a simple text panel
            return Panel(
                f"Error creating load panel: {e}",
                title="Load Monitor Error",
                border_style="red",
            )

    async def start_load_monitor(self, interval: int = 2, use_rich: bool = True):
        """Start real-time load monitoring"""
        if not use_rich:
            logger.info("Load monitoring started - using simple mode")

            async def simple_monitor_loop():
                try:
                    while True:
                        await self.update_all_server_loads()
                        stats = self.get_load_stats()
                        logger.opt(extra={"status_update": True}).info(
                            f"Load Status: Total Load: {stats['summary']['total_active_load']}, "
                            f"Utilization: {stats['summary']['overall_utilization']:.1f}%"
                        )
                        await asyncio.sleep(interval)
                except asyncio.CancelledError:
                    logger.info("Simple load monitoring stopped")
                except Exception as e:
                    logger.error(f"Simple load monitoring error: {e}")

            self.monitor_task = asyncio.create_task(simple_monitor_loop())
            return

        if self.fullscreen_mode:
            logger.info("Load monitoring started - fullscreen Rich Live mode")
        else:
            logger.info("Load monitoring started - Rich Live mode")

        async def rich_monitor_loop():
            try:
                # Initialize panel
                initial_panel = self.create_load_status_panel()

                # Fullscreen mode uses different display parameters
                if self.fullscreen_mode:
                    # Fullscreen mode: vertical centering, auto-adjust size
                    with Live(
                        initial_panel,
                        refresh_per_second=1,
                        console=self.console,
                        vertical_overflow="visible",
                        screen=True,
                    ) as live:
                        while True:
                            try:
                                await self.update_all_server_loads()
                                new_panel = self.create_load_status_panel()
                                live.update(new_panel)
                                await asyncio.sleep(interval)
                            except Exception as e:
                                logger.error(f"Error updating load panel: {e}")
                                await asyncio.sleep(interval)
                else:
                    # Normal mode: maintain original behavior
                    with Live(
                        initial_panel, refresh_per_second=1, console=self.console
                    ) as live:
                        while True:
                            try:
                                await self.update_all_server_loads()
                                new_panel = self.create_load_status_panel()
                                live.update(new_panel)
                                await asyncio.sleep(interval)
                            except Exception as e:
                                logger.error(f"Error updating load panel: {e}")
                                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                if self.fullscreen_mode:
                    logger.info("Fullscreen Rich Live load monitoring stopped")
                else:
                    logger.info("Rich Live load monitoring stopped")
            except Exception as e:
                if self.fullscreen_mode:
                    logger.error(
                        f"Fullscreen Rich Live load monitoring initialization error: {e}"
                    )
                else:
                    logger.error(f"Rich Live load monitoring initialization error: {e}")

        self.monitor_task = asyncio.create_task(rich_monitor_loop())
        logger.info(f"Real-time load monitoring started, interval: {interval} seconds")

    async def stop_load_monitor(self):
        """Stop load monitoring"""
        if hasattr(self, "monitor_task") and self.monitor_task:
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass
            logger.info("Load monitoring stopped")


# Global load manager instance
_global_load_manager = None


def get_load_manager(
    fullscreen_mode: bool = False, show_models: bool = False
) -> LoadManager:
    """Get global load manager instance"""
    global _global_load_manager
    if _global_load_manager is None:
        config = get_config()
        _global_load_manager = LoadManager(
            config, fullscreen_mode=fullscreen_mode, show_models=show_models
        )
        logger.info(
            f"Global load manager instance created (fullscreen={fullscreen_mode}, show_models={show_models})"
        )
    return _global_load_manager
