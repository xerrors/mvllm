import asyncio
import httpx
import random
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import StreamingResponse, JSONResponse
from typing import Union, List
from loguru import logger
from .config import Config, get_config
from .load_manager import LoadManager, get_load_manager

router = APIRouter()

async def _select_optimal_server(config: Config, load_manager: LoadManager) -> str:
    """选择当前负载最小的健康服务器"""
    healthy_servers = config.get_healthy_servers()

    if not healthy_servers:
        raise HTTPException(status_code=503, detail="No healthy servers available")

    # 获取实时负载数据
    load_stats = load_manager.get_load_stats()

    # 计算每个服务器的综合得分（负载+可用容量）
    candidates_under_threshold: List = []  # 存储score < 0.5的服务器
    best_servers: List = []  # 存储得分相同的服务器（后备选择）
    best_score = float('inf')

    for server in healthy_servers:
        server_load_info = load_stats["server_loads"].get(server.url, {})
        detailed_metrics = server_load_info.get("detailed_metrics", {})
        max_capacity = server_load_info.get("max_capacity", 3)

        # 获取详细负载数据和容量
        running = detailed_metrics.get("num_requests_running", 0)
        waiting = detailed_metrics.get("num_requests_waiting", 0)
        capacity = max_capacity

        # 计算相对负载（考虑服务器容量）
        # 综合得分：Running 权重更高，除以容量确保公平比较
        if capacity > 0:
            score = (running + waiting * 0.5) / capacity
        else:
            score = float('inf')  # 容量为0的服务器不应该被选择

        # 收集score < 0.5的服务器
        if score < 0.5:
            candidates_under_threshold.append(server)

        # 同时记录最佳得分的服务器作为后备
        if score < best_score:
            best_score = score
            best_servers = [server]  # 重置列表，只包含当前最佳服务器
        elif score == best_score:
            best_servers.append(server)  # 添加得分相同的服务器

    # 优先选择score < 0.5的服务器
    if candidates_under_threshold:
        selected_server = random.choice(candidates_under_threshold)
        selected_metrics = load_stats['server_loads'][selected_server.url]['detailed_metrics']
        logger.info(f"Selected server {selected_server.url} from {len(candidates_under_threshold)} candidates under threshold (score < 0.5) - Running: {selected_metrics['num_requests_running']}, Waiting: {selected_metrics['num_requests_waiting']}")
        return selected_server.url

    # 如果没有score < 0.5的服务器，选择得分最小的
    if best_servers:
        selected_server = random.choice(best_servers)
        selected_metrics = load_stats['server_loads'][selected_server.url]['detailed_metrics']
        logger.info(f"Selected server {selected_server.url} from {len(best_servers)} candidates with best score {best_score} - Running: {selected_metrics['num_requests_running']}, Waiting: {selected_metrics['num_requests_waiting']}")
        return selected_server.url

    # 理论上不会到达这里
    selected = healthy_servers[0]
    logger.info(f"Randomly selected server {selected.url}")
    return selected.url

async def _forward_request_with_retry(
    request: Request,
    path: str,
    method: str,
    config: Config,
    load_manager: LoadManager
) -> Union[JSONResponse, StreamingResponse]:
    """
    直接转发请求到最优服务器，支持重试逻辑
    """
    # 获取请求体和头部信息
    body = await request.body()
    headers = dict(request.headers)
    headers.pop('host', None)  # 避免头部冲突

    retries = 0
    max_retries = config.app_config.max_retries

    while retries <= max_retries:
        try:
            # 选择最优服务器
            server_url = await _select_optimal_server(config, load_manager)
            target_url = f"{server_url}{path}"

            logger.info(f"Forwarding {method} {path} to {target_url} (attempt {retries + 1}/{max_retries + 1})")

            # 转发请求
            async with httpx.AsyncClient(timeout=config.app_config.request_timeout) as client:
                response = await client.request(
                    method=method,
                    url=target_url,
                    content=body,
                    headers=headers
                )

            response.raise_for_status()  # 检查响应状态

            # 处理成功的响应
            if response.headers.get('content-type', '').startswith('text/event-stream'):
                # 流式响应
                async def stream_response():
                    try:
                        async for chunk in response.aiter_bytes():
                            yield chunk
                    except Exception as e:
                        logger.error(f"Error streaming response from {server_url}: {e}")
                    finally:
                        logger.info(f"Stream completed for {method} {path} from {server_url}")

                return StreamingResponse(
                    stream_response(),
                    status_code=response.status_code,
                    headers=dict(response.headers)
                )
            else:
                # JSON响应
                logger.info(f"Request {method} {path} completed successfully on {server_url}")
                return JSONResponse(
                    content=response.json(),
                    status_code=response.status_code,
                    headers=dict(response.headers)
                )

        except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPStatusError) as e:
            logger.warning(f"Request failed on {server_url}: {e}")

            # 标记服务器为不健康
            config.update_server_health(server_url, False)

            if retries >= max_retries:
                logger.error(f"Request {method} {path} exceeded max retry count ({max_retries})")
                raise HTTPException(status_code=502, detail="Bad gateway - max retries exceeded")

            retries += 1
            logger.info(f"Retrying request (attempt {retries}/{max_retries})")
            # 等待一段时间再重试
            await asyncio.sleep(0.1)

        except Exception as e:
            logger.error(f"Unexpected error for request {method} {path}: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    # 理论上不应该到达这里
    raise HTTPException(status_code=500, detail="Internal server error: Unexpected flow in request forwarding")

@router.post("/chat/completions")
async def chat_completions(
    request: Request,
    config: Config = Depends(get_config),
    load_manager: LoadManager = Depends(get_load_manager)
):
    """OpenAI-compatible chat completions endpoint"""
    return await _forward_request_with_retry(
        request=request,
        path="/v1/chat/completions",
        method="POST",
        config=config,
        load_manager=load_manager
    )

@router.post("/completions")
async def completions(
    request: Request,
    config: Config = Depends(get_config),
    load_manager: LoadManager = Depends(get_load_manager)
):
    """OpenAI-compatible completions endpoint"""
    return await _forward_request_with_retry(
        request=request,
        path="/v1/completions",
        method="POST",
        config=config,
        load_manager=load_manager
    )

@router.get("/models")
async def models(
    request: Request,
    config: Config = Depends(get_config),
    load_manager: LoadManager = Depends(get_load_manager)
):
    """OpenAI-compatible models endpoint"""
    return await _forward_request_with_retry(
        request=request,
        path="/v1/models",
        method="GET",
        config=config,
        load_manager=load_manager
    )

@router.post("/embeddings")
async def embeddings(
    request: Request,
    config: Config = Depends(get_config),
    load_manager: LoadManager = Depends(get_load_manager)
):
    """OpenAI-compatible embeddings endpoint"""
    return await _forward_request_with_retry(
        request=request,
        path="/v1/embeddings",
        method="POST",
        config=config,
        load_manager=load_manager
    )

@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def openai_fallback(
    path: str,
    request: Request,
    config: Config = Depends(get_config),
    load_manager: LoadManager = Depends(get_load_manager)
):
    """Fallback route for any other OpenAI-compatible endpoints"""
    # 确保路径以 /v1/ 开头
    final_path = f"/v1/{path}" if not path.startswith("v1/") else f"/{path}"

    return await _forward_request_with_retry(
        request=request,
        path=final_path,
        method=request.method,
        config=config,
        load_manager=load_manager
    )