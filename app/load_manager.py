"""
Real-time load management for vLLM Router
"""

import asyncio
import aiohttp
import sys
from datetime import datetime
from typing import Dict, Optional, List
from loguru import logger
from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from .config import Config, get_config

class LoadManager:
    def __init__(self, config: Config):
        self.config = config
        self.server_loads: Dict[str, dict] = {}  # 服务器负载指标字典
        self.server_status: Dict[str, bool] = {}  # 服务器状态
        self.last_updated: Dict[str, datetime] = {}  # 最后更新时间
        self.load_check_lock = asyncio.Lock()

        # Rich console for status display
        self.console = Console(file=sys.stdout)
        self.live_display = None

        # 初始化服务器状态
        self._initialize_servers()

    def _initialize_servers(self):
        """初始化所有服务器状态"""
        for server in self.config.servers:
            self.server_loads[server.url] = {
                'num_requests_running': 0,
                'num_requests_waiting': 0,
                'gpu_cache_usage_perc': 0.0,
                'process_max_fds': 65535,
                'system_load': 0
            }
            self.server_status[server.url] = True  # 默认健康
            self.last_updated[server.url] = datetime.now()

    async def get_server_load(self, server_url: str) -> Optional[dict]:
        """获取指定服务器的实时负载（使用/metrics接口）"""
        try:
            # 使用服务器提供的 /metrics 接口获取实际负载
            metrics_url = f"{server_url}/metrics"

            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                async with session.get(metrics_url) as response:
                    if response.status == 200:
                        metrics_text = await response.text()
                        load_metrics = self._parse_vllm_metrics(metrics_text)
                        logger.debug(f"Got load metrics from {server_url}: {load_metrics['system_load']}")
                        return load_metrics
                    else:
                        logger.warning(f"Failed to get metrics from {server_url}, status: {response.status}")
                        return None
        except Exception as e:
            logger.error(f"Error getting load from {server_url}: {e}")
            return None

    def _parse_vllm_metrics(self, metrics_text: str) -> dict:
        """解析vLLM metrics数据，提取多个指标"""
        try:
            metrics = {
                'num_requests_running': 0,
                'num_requests_waiting': 0,
                'gpu_cache_usage_perc': 0.0,
                'process_max_fds': 65535,  # 默认值
                'system_load': 0  # 计算得出的综合负载
            }

            for line in metrics_text.split('\n'):
                line = line.strip()
                if not line or line.startswith('#'):
                    continue

                # 解析不同指标
                if line.startswith('vllm:num_requests_running'):
                    value = self._extract_metric_value(line)
                    if value is not None:
                        metrics['num_requests_running'] = int(value)

                elif line.startswith('vllm:num_requests_waiting'):
                    value = self._extract_metric_value(line)
                    if value is not None:
                        metrics['num_requests_waiting'] = int(value)

                elif line.startswith('vllm:gpu_cache_usage_perc'):
                    value = self._extract_metric_value(line)
                    if value is not None:
                        metrics['gpu_cache_usage_perc'] = float(value)

                elif line.startswith('process_max_fds'):
                    value = self._extract_metric_value(line)
                    if value is not None:
                        metrics['process_max_fds'] = int(value)

            # 计算综合负载：正在运行的 + 等待中的，但不超过最大文件描述符限制
            total_requests = metrics['num_requests_running'] + metrics['num_requests_waiting']
            # 根据系统文件描述符限制调整负载权重
            max_concurrent_by_fds = max(1, metrics['process_max_fds'] // 1000)  # 估算最大并发数
            metrics['system_load'] = min(total_requests, max_concurrent_by_fds)

            logger.debug(f"Parsed metrics: running={metrics['num_requests_running']}, "
                        f"waiting={metrics['num_requests_waiting']}, "
                        f"gpu_cache={metrics['gpu_cache_usage_perc']:.1f}%, "
                        f"max_fds={metrics['process_max_fds']}, "
                        f"system_load={metrics['system_load']}")

            return metrics

        except Exception as e:
            logger.error(f"Error parsing vLLM metrics: {e}")
            return {
                'num_requests_running': 0,
                'num_requests_waiting': 0,
                'gpu_cache_usage_perc': 0.0,
                'process_max_fds': 65535,
                'system_load': 0
            }

    def _extract_metric_value(self, line: str) -> float:
        """从metrics行中提取数值"""
        try:
            # 解析类似: vllm:num_requests_running{engine="0",model_name="llama3.1:8b"} 15.0
            parts = line.split(' ')
            if len(parts) >= 2:
                return float(parts[-1])
        except (ValueError, IndexError):
            pass
        return None

    async def update_all_server_loads(self):
        """更新所有服务器的负载信息"""
        async with self.load_check_lock:
            tasks = []
            for server in self.config.servers:
                if server.is_healthy:  # 只检查健康的服务器
                    tasks.append(self._update_single_server_load(server.url))

            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

    async def _update_single_server_load(self, server_url: str):
        """更新单个服务器的负载"""
        try:
            load = await self.get_server_load(server_url)
            if load is not None:
                self.server_loads[server_url] = load
                self.server_status[server_url] = True
                self.last_updated[server_url] = datetime.now()
            else:
                self.server_status[server_url] = False
                logger.warning(f"Failed to get metrics from {server_url}")
        except Exception as e:
            self.server_status[server_url] = False
            logger.error(f"Error updating load for {server_url}: {e}")

    def get_load_stats(self) -> dict:
        """获取负载统计信息"""
        healthy_servers = self.config.get_healthy_servers()

        return {
            "total_servers": len(self.config.servers),
            "healthy_servers": len(healthy_servers),
            "server_loads": {
                server.url: {
                    "current_load": self.server_loads.get(server.url, {}).get('system_load', 0),
                    "max_capacity": server.max_concurrent_requests,
                    "available_capacity": max(0, server.max_concurrent_requests - self.server_loads.get(server.url, {}).get('system_load', 0)),
                    "utilization": min(100, (self.server_loads.get(server.url, {}).get('system_load', 0) / server.max_concurrent_requests * 100)) if server.max_concurrent_requests > 0 else 0,
                    "status": self.server_status.get(server.url, False),
                    "last_updated": self.last_updated.get(server.url, None).isoformat() if self.last_updated.get(server.url, None) else None,
                    "detailed_metrics": {
                        "num_requests_running": self.server_loads.get(server.url, {}).get('num_requests_running', 0),
                        "num_requests_waiting": self.server_loads.get(server.url, {}).get('num_requests_waiting', 0),
                        "gpu_cache_usage_perc": self.server_loads.get(server.url, {}).get('gpu_cache_usage_perc', 0.0),
                        "process_max_fds": self.server_loads.get(server.url, {}).get('process_max_fds', 65535)
                    }
                }
                for server in self.config.servers
            },
            "summary": {
                "total_active_load": sum(metrics.get('system_load', 0) for metrics in self.server_loads.values()),
                "total_capacity": sum(server.max_concurrent_requests for server in self.config.servers),
                "overall_utilization": sum(metrics.get('system_load', 0) for metrics in self.server_loads.values()) / sum(server.max_concurrent_requests for server in self.config.servers) * 100 if sum(server.max_concurrent_requests for server in self.config.servers) > 0 else 0
            }
        }

    def create_load_status_panel(self):
        """创建负载状态面板"""
        try:
            stats = self.get_load_stats()

            # 创建主表格 - 显示详细的负载数据（不显示Load列，因为已有Running+Waiting）
            table = Table(show_header=True, header_style="bold blue", box=None)
            table.add_column("Time", style="cyan", no_wrap=True)
            table.add_column("Server", style="green")
            table.add_column("Running", style="yellow", justify="right")
            table.add_column("Waiting", style="bright_yellow", justify="right")
            table.add_column("Capacity", style="magenta", justify="right")
            table.add_column("Usage", style="cyan", justify="right")
            table.add_column("Status", style="blue", justify="center")

            # 服务器负载信息
            server_rows = []
            for server in self.config.servers:
                server_name = server.url.split("://")[-1].split(":")[0]
                load_info = stats["server_loads"][server.url]
                current_load = load_info["current_load"]
                max_capacity = load_info["max_capacity"]
                utilization = load_info["utilization"]
                status = load_info["status"]

                # 获取详细指标
                detailed_metrics = load_info["detailed_metrics"]
                running = detailed_metrics["num_requests_running"]
                waiting = detailed_metrics["num_requests_waiting"]

                # 根据负载状态设置颜色和图标
                if not status:
                    status_icon = "❌"
                    # 为不健康的服务器添加删除线
                    server_name = f"[red strike]{server_name}[/red strike]"
                    running_str = f"[red]{running}[/red]"
                    waiting_str = f"[red]{waiting}[/red]"
                    current_load_str = f"[red]{current_load}[/red]"
                    utilization_str = f"[red]{utilization:.1f}%[/red]"
                elif utilization >= 90:
                    status_icon = "🔴"
                    server_name = f"[red]{server_name}[/red]"
                    running_str = f"[red]{running}[/red]"
                    waiting_str = f"[red]{waiting}[/red]"
                    current_load_str = f"[red]{current_load}[/red]"
                    utilization_str = f"[red]{utilization:.1f}%[/red]"
                elif utilization >= 70:
                    status_icon = "🟡"
                    server_name = f"[yellow]{server_name}[/yellow]"
                    running_str = f"[bright_yellow]{running}[/bright_yellow]"
                    waiting_str = f"[bright_yellow]{waiting}[/bright_yellow]"
                    current_load_str = f"[yellow]{current_load}[/yellow]"
                    utilization_str = f"[yellow]{utilization:.1f}%[/yellow]"
                else:
                    status_icon = "✅"
                    server_name = f"[green]{server_name}[/green]"
                    running_str = f"[green]{running}[/green]"
                    waiting_str = f"[green]{waiting}[/green]"
                    current_load_str = f"[green]{current_load}[/green]"
                    utilization_str = f"[green]{utilization:.1f}%[/green]"

                server_rows.append((
                    f"{datetime.now().strftime('%H:%M:%S')}",
                    server_name,
                    running_str,
                    waiting_str,
                    f"{max_capacity}",
                    utilization_str,
                    status_icon
                ))

            # 添加服务器行
            for row in server_rows:
                table.add_row(*row)

            # 计算总体状态
            overall_utilization = stats["summary"]["overall_utilization"]
            healthy_count = stats["healthy_servers"]
            total_servers = stats["total_servers"]

            # 计算总体的 running 和 waiting 数量
            total_running = sum(load_info["detailed_metrics"]["num_requests_running"] for load_info in stats["server_loads"].values())
            total_waiting = sum(load_info["detailed_metrics"]["num_requests_waiting"] for load_info in stats["server_loads"].values())

            if total_servers == 0:
                health_status = "No servers"
            elif healthy_count == total_servers:
                health_status = "All healthy"
            elif healthy_count >= total_servers * 0.7:
                health_status = "Partially healthy"
            else:
                health_status = "Mostly unhealthy"

            # 创建主面板 - 显示详细的总计信息
            panel = Panel(
                table,
                title="vLLM Router - Real-time Load Monitor",
                subtitle=f"Health: {healthy_count}/{total_servers} | {health_status} | Running: {total_running} | Waiting: {total_waiting} | Total Usage: {overall_utilization:.1f}%",
                border_style="blue"
            )

            return panel

        except Exception as e:
            # 如果创建表格失败，返回一个简单的文本面板
            return Panel(f"Error creating load panel: {e}", title="Load Monitor Error", border_style="red")

    async def start_load_monitor(self, interval: int = 2, use_rich: bool = True):
        """启动实时负载监控"""
        if not use_rich:
            logger.info("负载监控已启动 - 使用简单模式")
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
                    logger.info("简单负载监控已停止")
                except Exception as e:
                    logger.error(f"简单负载监控出错: {e}")

            self.monitor_task = asyncio.create_task(simple_monitor_loop())
            return

        logger.info("负载监控已启动 - 使用Rich Live模式")

        async def rich_monitor_loop():
            try:
                # 初始化面板
                initial_panel = self.create_load_status_panel()
                with Live(initial_panel, refresh_per_second=1, console=self.console) as live:
                    while True:
                        try:
                            await self.update_all_server_loads()
                            new_panel = self.create_load_status_panel()
                            live.update(new_panel)
                            await asyncio.sleep(interval)
                        except Exception as e:
                            logger.error(f"更新负载面板时出错: {e}")
                            # 继续运行，不要因为一次错误而停止
                            await asyncio.sleep(interval)
            except asyncio.CancelledError:
                logger.info("Rich Live负载监控已停止")
            except Exception as e:
                logger.error(f"Rich Live负载监控初始化出错: {e}")

        self.monitor_task = asyncio.create_task(rich_monitor_loop())
        logger.info(f"实时负载监控已启动，间隔: {interval}秒")

    async def stop_load_monitor(self):
        """停止负载监控"""
        if hasattr(self, 'monitor_task') and self.monitor_task:
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass
            logger.info("负载监控已停止")

# 全局负载管理器实例
_global_load_manager = None

def get_load_manager() -> LoadManager:
    """获取全局负载管理器实例"""
    global _global_load_manager
    if _global_load_manager is None:
        config = get_config()
        _global_load_manager = LoadManager(config)
        logger.info("Global load manager instance created")
    return _global_load_manager