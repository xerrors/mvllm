import asyncio
import httpx
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import StreamingResponse, JSONResponse
from typing import Union
from loguru import logger
import uuid
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
    best_server = None
    best_score = float('inf')

    for server in healthy_servers:
        server_load_info = load_stats["server_loads"].get(server.url, {})
        current_load = server_load_info.get("current_load", 0)
        max_capacity = server_load_info.get("max_capacity", 3)
        utilization = server_load_info.get("utilization", 0)

        # 综合得分：主要考虑当前负载，其次是利用率
        score = current_load * 2 + utilization * 0.01

        if score < best_score:
            best_score = score
            best_server = server

    if best_server:
        logger.info(f"Selected server {best_server.url} with load {load_stats['server_loads'][best_server.url].get('current_load', 0)}/{load_stats['server_loads'][best_server.url].get('max_capacity', 3)}")
        return best_server.url

    # 如果没有找到最佳服务器（理论上不会发生），随机选择一个健康服务器
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