import asyncio
import httpx
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import StreamingResponse, JSONResponse
from typing import Union
from loguru import logger
import uuid # Added import for uuid
from .config import Config, get_config
from .queue_manager import QueueManager, get_queue_manager

router = APIRouter()

async def _forward_request_with_retry(
    request: Request,
    path: str,
    method: str,
    config: Config,
    queue_manager: QueueManager
) -> Union[JSONResponse, StreamingResponse]:
    """
    Forwards a request to a backend server with queue-based load balancing and retry logic.
    """
    # Get request body and headers once
    body = await request.body()
    headers = dict(request.headers)
    headers.pop('host', None)  # Avoid host header issues

    # Create request data for queue
    request_data = {
        'method': method,
        'path': path,
        'body': body,
        'headers': headers,
        'timestamp': asyncio.get_event_loop().time(),
        'retry_count': 0 # Initialize retry count
    }

    # Generate a unique ID for this request attempt
    request_id = str(uuid.uuid4())
    request_data['request_id'] = request_id
    await queue_manager.add_request(request_data)
    logger.info(f"Request {request_id} added to queue for {method} {path}")

    retries = 0
    max_retries = config.app_config.max_retries

    while retries <= max_retries:
        server_url = await queue_manager.wait_for_dispatch(request_id, timeout=config.app_config.request_timeout)

        if not server_url:
            logger.error(f"Request {request_id} failed to be dispatched within timeout after {retries} retries.")
            # If it's the last retry, raise an error. Otherwise, the loop will continue.
            if retries == max_retries:
                raise HTTPException(status_code=504, detail="Request dispatch timeout")
            else:
                # If dispatch times out, it means no server was available or the worker didn't pick it up.
                # We should increment retry count and re-queue.
                retries += 1
                request_data['retry_count'] = retries
                await queue_manager.redistribute_request(request_id, request_data)
                continue # Try again

        # Get server config
        server = config.get_server_by_url(server_url)
        if not server:
            logger.error(f"Server {server_url} not found in configuration for request {request_id}.")
            # This is an internal error, not a retryable one for the client.
            raise HTTPException(status_code=500, detail="Internal server error: Server not found.")

        target_url = f"{server.url}{path}"
        logger.info(f"Processing request {request_id} on {target_url} (attempt {retries + 1}/{max_retries + 1})")

        try:
            async with httpx.AsyncClient(timeout=config.app_config.request_timeout) as client:
                response = await client.request(
                    method=method,
                    url=target_url,
                    content=body,
                    headers=headers
                )
            response.raise_for_status()  # Raise an exception for 4xx or 5xx status codes

            # Success! Handle response and exit loop.
            if response.headers.get('content-type', '').startswith('text/event-stream'):
                async def stream_response():
                    try:
                        async for chunk in response.aiter_bytes():
                            yield chunk
                    finally:
                        try:
                            await queue_manager.notify_request_completed(request_id)
                            logger.info(f"Stream completed for request {request_id}")
                        except Exception as e:
                            logger.error(f"Failed to notify completion for request {request_id}: {e}")

                return StreamingResponse(
                    stream_response(),
                    status_code=response.status_code,
                    headers=dict(response.headers)
                )
            else:
                try:
                    await queue_manager.notify_request_completed(request_id)
                    logger.info(f"Request {request_id} completed successfully")
                except Exception as e:
                    logger.error(f"Failed to notify completion for request {request_id}: {e}")

                return JSONResponse(
                    content=response.json(),
                    status_code=response.status_code,
                    headers=dict(response.headers)
                )

        except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPStatusError) as e:
            logger.warning(f"Request {request_id} failed on {server.url}: {e}. Updating health status and retrying.")

            # Mark server as unhealthy
            config.update_server_health(server.url, False)

            # Release the request from current server's load count
            try:
                await queue_manager.notify_request_completed(request_id)
                logger.info(f"Request {request_id} released from failed server {server.url}")
            except Exception as completion_error:
                logger.error(f"Failed to notify completion for failed request {request_id}: {completion_error}")

            if retries >= max_retries:
                logger.error(f"Request {request_id} exceeded max retry count ({max_retries}).")
                raise HTTPException(status_code=502, detail="Bad gateway - max retries exceeded")

            retries += 1
            request_data['retry_count'] = retries
            logger.info(f"Re-queueing request {request_id} for retry (attempt {retries}/{max_retries}).")
            await queue_manager.redistribute_request(request_id, request_data)
            # Continue the while loop for the next retry attempt
        except Exception as e:
            logger.error(f"An unexpected error occurred for request {request_id}: {e}")
            # Ensure the request is released even on unexpected errors
            try:
                await queue_manager.notify_request_completed(request_id)
            except Exception as completion_error:
                logger.error(f"Failed to notify completion for request {request_id} on unexpected error: {completion_error}")
            raise HTTPException(status_code=500, detail="Internal server error")

    # This part should ideally not be reached if retries are handled correctly or an exception is raised.
    raise HTTPException(status_code=500, detail="Internal server error: Unexpected flow in request forwarding.")


@router.post("/chat/completions")
async def chat_completions(
    request: Request,
    config: Config = Depends(get_config),
    queue_manager: QueueManager = Depends(get_queue_manager)
):
    """OpenAI-compatible chat completions endpoint"""
    return await _forward_request_with_retry(
        request=request,
        path="/v1/chat/completions",
        method="POST",
        config=config,
        queue_manager=queue_manager
    )

@router.post("/completions")
async def completions(
    request: Request,
    config: Config = Depends(get_config),
    queue_manager: QueueManager = Depends(get_queue_manager)
):
    """OpenAI-compatible completions endpoint"""
    return await _forward_request_with_retry(
        request=request,
        path="/v1/completions",
        method="POST",
        config=config,
        queue_manager=queue_manager
    )

@router.get("/models")
async def models(
    request: Request,
    config: Config = Depends(get_config),
    queue_manager: QueueManager = Depends(get_queue_manager)
):
    """OpenAI-compatible models endpoint"""
    return await _forward_request_with_retry(
        request=request,
        path="/v1/models",
        method="GET",
        config=config,
        queue_manager=queue_manager
    )

@router.post("/embeddings")
async def embeddings(
    request: Request,
    config: Config = Depends(get_config),
    queue_manager: QueueManager = Depends(get_queue_manager)
):
    """OpenAI-compatible embeddings endpoint"""
    return await _forward_request_with_retry(
        request=request,
        path="/v1/embeddings",
        method="POST",
        config=config,
        queue_manager=queue_manager
    )

@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def openai_fallback(
    path: str,
    request: Request,
    config: Config = Depends(get_config),
    queue_manager: QueueManager = Depends(get_queue_manager)
):
    """Fallback route for any other OpenAI-compatible endpoints"""
    # Ensure the path starts with /v1/
    final_path = f"/v1/{path}" if not path.startswith("v1/") else f"/{path}"

    return await _forward_request_with_retry(
        request=request,
        path=final_path,
        method=request.method,
        config=config,
        queue_manager=queue_manager
    )

@router.post("/release_request")
async def release_request(
    request_data: dict,
    queue_manager: QueueManager = Depends(get_queue_manager)
):
    """手动释放请求（当vLLM服务器真正完成请求处理时调用）"""
    request_id = request_data.get("request_id")
    if not request_id:
        raise HTTPException(status_code=400, detail="Missing request_id")

    await queue_manager.release_request(request_id)
    return {"status": "success", "message": f"Request {request_id} released"}

@router.post("/notify_completion")
async def notify_completion(
    completion_data: dict,
    queue_manager: QueueManager = Depends(get_queue_manager)
):
    """vLLM服务器完成请求处理后的回调端点"""
    request_id = completion_data.get("request_id")
    server_url = completion_data.get("server_url")

    if not request_id:
        raise HTTPException(status_code=400, detail="Missing request_id")

    # 如果提供了server_url，验证请求确实来自该服务器
    if server_url and request_id in queue_manager.active_requests:
        actual_server = queue_manager.active_requests[request_id]
        if actual_server != server_url:
            logger.warning(f"Server URL mismatch for request {request_id}: expected {actual_server}, got {server_url}")

    # 通知队列管理器请求已完成
    await queue_manager.notify_request_completed(request_id)

    return {"status": "success", "message": f"Request {request_id} completion acknowledged"}
