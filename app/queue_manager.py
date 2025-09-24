"""
Queue management for vLLM Router
"""

import asyncio
import random
import sys
import uuid
from datetime import datetime
from typing import Dict, Optional
from loguru import logger
from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.progress import Progress, SpinnerColumn, TextColumn
from .config import Config, get_config

class QueueManager:
    def __init__(self, config: Config):
        self.config = config
        self.global_queue = asyncio.Queue()  # 全局队列，所有请求按FIFO顺序处理
        self.server_loads: Dict[str, int] = {}  # 服务器当前处理中的请求数量
        self.server_locks: Dict[str, asyncio.Lock] = {}  # 每个服务器的锁
        self.lock = asyncio.Lock()  # 全局锁
        self.active_requests: Dict[str, str] = {}  # request_id -> server_url 映射
        self.request_events: Dict[str, asyncio.Event] = {}  # 请求分发事件
        self.completed_requests = asyncio.Queue()  # 已完成的请求队列

        # Rich console for status display - force stdout to avoid conflicts with loguru
        self.console = Console(file=sys.stdout)
        self.live_display = None

        # 初始化服务器状态
        self._initialize_servers()

        # 启动分发工作器
        self._worker_started = False

    def _initialize_servers(self):
        """初始化所有服务器状态"""
        for server in self.config.servers:
            self.server_loads[server.url] = 0
            self.server_locks[server.url] = asyncio.Lock()

    async def add_request(self, request_data: dict) -> str:
        """添加请求到全局队列并返回请求ID"""
        request_id = request_data['request_id'] # Use the request_id from request_data

        # 添加到全局队列
        await self.global_queue.put(request_data)

        # 创建请求事件
        self.request_events[request_id] = asyncio.Event()

        logger.info(f"Request {request_id} added to global queue. Queue size: {self.global_queue.qsize()}")

        # 启动分发任务（如果还没有启动）
        if not getattr(self, '_worker_started', False):
            self._worker_started = True
            logger.info("Starting dispatch worker for the first time...")
            asyncio.create_task(self._dispatch_worker())
        return request_id

    async def _dispatch_worker(self):
        """持续处理全局队列中的请求分发"""
        logger.info("Starting dispatch worker...")

        while True:
            try:
                # 从全局队列获取请求
                request_data = await self.global_queue.get()
                request_id = request_data.get('request_id')

                logger.info(f"Dispatch worker processing request {request_id}, queue size: {self.global_queue.qsize()}")

                # 选择最优服务器
                server_url = await self._select_optimal_server()

                if server_url:
                    # 分发请求到服务器
                    await self._dispatch_to_server(request_id, server_url, request_data)
                    logger.info(f"Request {request_id} dispatched to {server_url}")
                else:
                    logger.warning(f"No servers have available capacity for request {request_id}. Re-queueing.")
                    # 等待一段时间再重新尝试
                    await asyncio.sleep(0.1) # Small delay before re-queueing
                    # 将请求放回队列尾部
                    await self.global_queue.put(request_data)

            except asyncio.CancelledError:
                logger.info("Dispatch worker cancelled")
                break
            except Exception as e:
                logger.error(f"Error in dispatch worker: {e}")
                # 继续处理下一个请求，不要因为一个错误而停止
                continue

    async def _select_optimal_server(self) -> Optional[str]:
        """选择当前负载最小的健康服务器，考虑最大并发限制"""
        healthy_servers = self.config.get_healthy_servers()

        logger.debug(f"Selecting optimal server from {len(healthy_servers)} healthy servers")

        if not healthy_servers:
            logger.warning("No healthy servers available")
            return None

        # 找到有可用容量的服务器，计算负载百分比
        available_servers = []
        for server in healthy_servers:
            current_load = self.server_loads.get(server.url, 0)
            max_concurrent = server.max_concurrent_requests
            available_capacity = max_concurrent - current_load
            load_percentage = current_load / max_concurrent if max_concurrent > 0 else 0

            logger.debug(f"Server {server.url} has load {current_load}/{max_concurrent} ({load_percentage:.1%}) (available: {available_capacity})")

            if available_capacity > 0:
                available_servers.append((server.url, current_load, load_percentage))

        if not available_servers:
            logger.debug("No servers have available capacity")
            return None

        # 选择负载百分比最小的服务器
        min_load_percentage = min(load_pct for _, _, load_pct in available_servers)
        selected_servers = [url for url, _, load_pct in available_servers if load_pct == min_load_percentage]

        logger.debug(f"Selected servers with min load percentage {min_load_percentage:.1%}: {selected_servers}")

        # 如果有多个服务器负载相同，随机选择一个
        if selected_servers:
            selected = random.choice(selected_servers)
            logger.info(f"Chose server {selected}")
            return selected

        logger.warning("No servers selected despite having available capacity")
        return None

    async def _dispatch_to_server(self, request_id: str, server_url: str, request_data: dict):
        """将请求分发到指定服务器"""
        async with self.server_locks[server_url]:
            # 更新服务器负载
            self.server_loads[server_url] += 1
            self.active_requests[request_id] = server_url

        # 触发请求分发事件
        if request_id in self.request_events:
            self.request_events[request_id].set()

        logger.info(f"Request {request_id} dispatched to {server_url}. Current load: {self.server_loads[server_url]}")

    async def wait_for_dispatch(self, request_id: str, timeout: float = 30.0) -> Optional[str]:
        """等待请求被分发到某个服务器"""
        try:
            if request_id not in self.request_events:
                logger.error(f"Request {request_id} not found in request events")
                return None

            # 等待分发事件
            await asyncio.wait_for(self.request_events[request_id].wait(), timeout=timeout)
            return self.active_requests.get(request_id)

        except asyncio.TimeoutError:
            logger.error(f"Request {request_id} dispatch timeout after {timeout}s")
            return None

    async def redistribute_request(self, request_id: str, request_data: dict):
        """Re-queues a failed request for redistribution to another server."""
        logger.info(f"Re-queueing request {request_id} for redistribution.")
        # Re-create the event for this request_id, as the previous one might have been set or cancelled.
        self.request_events[request_id] = asyncio.Event()
        # Put it back in the global queue
        await self.global_queue.put(request_data)

    async def notify_request_completed(self, request_id: str):
        """通知请求已完成，减少服务器负载"""
        logger.debug(f"Notifying request {request_id} completed")
        if request_id not in self.active_requests:
            logger.warning(f"Request {request_id} not found in active requests")
            return

        server_url = self.active_requests[request_id]

        async with self.server_locks[server_url]:
            # 减少服务器负载
            if self.server_loads[server_url] > 0:
                self.server_loads[server_url] -= 1

            # 清理请求记录
            del self.active_requests[request_id]
            if request_id in self.request_events:
                del self.request_events[request_id]

        logger.info(f"Request {request_id} completed on {server_url}. Current load: {self.server_loads[server_url]}")

    async def release_request(self, request_id: str) -> bool:
        """手动释放请求（当请求真正完成时调用）"""
        await self.notify_request_completed(request_id)
        return True

    def get_queue_stats(self) -> dict:
        """获取队列统计信息"""
        healthy_servers = self.config.get_healthy_servers()
        return {
            "global_queue_size": self.global_queue.qsize(),
            "active_requests": len(self.active_requests),
            "server_loads": {
                server.url: {
                    "current": self.server_loads.get(server.url, 0),
                    "max": server.max_concurrent_requests,
                    "available": server.max_concurrent_requests - self.server_loads.get(server.url, 0)
                }
                for server in self.config.servers
            },
            "healthy_servers": len(healthy_servers),
            "total_servers": len(self.config.servers)
        }

    def create_status_panel(self):
        """创建美观的状态面板"""
        stats = self.get_queue_stats()
        global_queue_size = stats["global_queue_size"]
        active_requests = stats["active_requests"]

        # 创建主表格
        table = Table(show_header=True, header_style="bold blue", box=None)
        table.add_column("时间", style="cyan", no_wrap=True)
        table.add_column("队列", style="green", justify="right")
        table.add_column("处理中", style="yellow", justify="right")
        table.add_column("服务器状态", style="magenta")

        # 服务器负载信息
        server_info = []
        healthy_servers = stats["healthy_servers"]
        total_servers = stats["total_servers"]

        for server_url, load_info in stats["server_loads"].items():
            server_name = server_url.split("://")[-1].split(":")[0]
            current = load_info["current"]
            max_concurrent = load_info["max"]
            available = load_info["available"]

            # 根据负载状态设置颜色
            if current == 0:
                status_icon = "✅"
            elif available == 0:
                status_icon = "🔴"
            else:
                status_icon = "🟡"

            server_info.append(f"{status_icon} {server_name}: {current}/{max_concurrent}")

        server_status = "\n".join(server_info) if server_info else "无服务器"

        # 添加数据行
        table.add_row(
            f"{datetime.now().strftime('%H:%M:%S')}",
            f"{global_queue_size}",
            f"{active_requests}",
            server_status
        )

        # 创建进度条显示健康状态
        healthy_ratio = healthy_servers / total_servers if total_servers > 0 else 0
        health_status = "健康" if healthy_ratio >= 0.8 else "部分健康" if healthy_ratio >= 0.5 else "不健康"

        # 创建主面板
        panel = Panel(
            table,
            title=f"[bold blue]vLLM Router[/bold blue]",
            subtitle=f"健康度: {healthy_servers}/{total_servers} | {health_status}",
            border_style="blue"
        )

        return panel

    async def start_status_monitor(self, interval: int = 5, use_rich: bool = True):
        """启动队列状态监控任务"""
        if not use_rich:
            logger.info("状态监控已启动 - 使用简单模式 (无Rich Live)")
            async def simple_monitor_loop():
                try:
                    while True:
                        # For simple mode, just log the stats or print a single line
                        stats = self.get_queue_stats()
                        logger.opt(extra={"status_update": True}).info(f"Queue Status: Global Queue: {stats['global_queue_size']}, Active: {stats['active_requests']}")
                        await asyncio.sleep(interval)
                except asyncio.CancelledError:
                    logger.info("简单状态监控已停止")
                except Exception as e:
                    logger.error(f"简单状态监控出错: {e}")
            self.monitor_task = asyncio.create_task(simple_monitor_loop())
            return

        logger.info("状态监控已启动 - 使用Rich Live模式")

        async def rich_monitor_loop():
            try:
                with Live(self.create_status_panel(), refresh_per_second=1, console=self.console) as live:
                    while True:
                        live.update(self.create_status_panel())
                        await asyncio.sleep(interval)
            except asyncio.CancelledError:
                logger.info("Rich Live状态监控已停止")
            except Exception as e:
                logger.error(f"Rich Live状态监控出错: {e}")

        self.monitor_task = asyncio.create_task(rich_monitor_loop())
        logger.info(f"队列状态监控已启动，间隔: {interval}秒")

    async def stop_status_monitor(self):
        """停止队列状态监控任务"""
        if hasattr(self, 'monitor_task') and self.monitor_task:
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass
            logger.info("队列状态监控已停止")

# 全局队列管理器实例
_global_queue_manager = None

def get_config():
    """Import get_config to avoid circular import"""
    from .config import get_config
    return get_config()

def get_queue_manager() -> QueueManager:
    """Get the global queue manager instance (singleton)"""
    global _global_queue_manager
    if _global_queue_manager is None:
        config = get_config()
        _global_queue_manager = QueueManager(config)
        logger.info("Global queue manager instance created")
    return _global_queue_manager
