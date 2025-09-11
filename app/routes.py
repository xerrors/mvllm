"""
OpenAI-compatible API routes for vLLM Router
"""

import httpx
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import StreamingResponse, JSONResponse
from typing import Union
from loguru import logger
from .config import Config
from .load_balancer import LoadBalancer
from .dependencies import get_config, get_load_balancer

router = APIRouter()

async def _forward_request_with_retry(
    request: Request,
    path: str,
    method: str,
    load_balancer: LoadBalancer,
    config: Config
) -> Union[JSONResponse, StreamingResponse]:
    """
    Forwards a request to a backend server with a retry mechanism.
    """
    last_exception = None
    
    # Get request body and headers once
    body = await request.body()
    headers = dict(request.headers)
    headers.pop('host', None) # Avoid host header issues

    for attempt in range(config.app_config.max_retries + 1):
        server = load_balancer.get_server()

        if not server:
            logger.error("No healthy servers available to forward request.")
            raise HTTPException(status_code=503, detail="No healthy servers available")

        target_url = f"{server.url}{path}"
        
        logger.info(
            f"Attempt {attempt + 1}/{config.app_config.max_retries + 1}: "
            f"Forwarding {method} {path} to {target_url}"
        )

        try:
            async with httpx.AsyncClient(timeout=config.app_config.request_timeout) as client:
                response = await client.request(
                    method=method,
                    url=target_url,
                    content=body,
                    headers=headers
                )
            
            response.raise_for_status() # Raise an exception for 4xx or 5xx status codes

            if response.headers.get('content-type', '').startswith('text/event-stream'):
                async def stream_response():
                    async for chunk in response.aiter_bytes():
                        yield chunk
                return StreamingResponse(
                    stream_response(),
                    status_code=response.status_code,
                    headers=dict(response.headers)
                )
            else:
                return JSONResponse(
                    content=response.json(),
                    status_code=response.status_code,
                    headers=dict(response.headers)
                )

        except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPStatusError) as e:
            last_exception = e
            logger.warning(f"Failed to forward request to {server.url}: {e}. Marking as unhealthy.")
            config.update_server_health(server.url, False)
            
            if attempt < config.app_config.max_retries:
                logger.info(f"Retrying request...")
            continue

    logger.error(f"Request failed after {config.app_config.max_retries + 1} attempts. Last error: {last_exception}")
    if isinstance(last_exception, httpx.TimeoutException):
        raise HTTPException(status_code=504, detail="Gateway timeout after multiple retries.")
    else:
        raise HTTPException(status_code=502, detail="Bad gateway after multiple retries.")


@router.post("/chat/completions")
async def chat_completions(
    request: Request,
    load_balancer: LoadBalancer = Depends(get_load_balancer),
    config: Config = Depends(get_config)
):
    """OpenAI-compatible chat completions endpoint"""
    return await _forward_request_with_retry(
        request=request,
        path="/v1/chat/completions",
        method="POST",
        load_balancer=load_balancer,
        config=config
    )

@router.post("/completions")
async def completions(
    request: Request,
    load_balancer: LoadBalancer = Depends(get_load_balancer),
    config: Config = Depends(get_config)
):
    """OpenAI-compatible completions endpoint"""
    return await _forward_request_with_retry(
        request=request,
        path="/v1/completions",
        method="POST",
        load_balancer=load_balancer,
        config=config
    )

@router.get("/models")
async def models(
    request: Request,
    load_balancer: LoadBalancer = Depends(get_load_balancer),
    config: Config = Depends(get_config)
):
    """OpenAI-compatible models endpoint"""
    return await _forward_request_with_retry(
        request=request,
        path="/v1/models",
        method="GET",
        load_balancer=load_balancer,
        config=config
    )

@router.post("/embeddings")
async def embeddings(
    request: Request,
    load_balancer: LoadBalancer = Depends(get_load_balancer),
    config: Config = Depends(get_config)
):
    """OpenAI-compatible embeddings endpoint"""
    return await _forward_request_with_retry(
        request=request,
        path="/v1/embeddings",
        method="POST",
        load_balancer=load_balancer,
        config=config
    )

@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def openai_fallback(
    path: str,
    request: Request,
    load_balancer: LoadBalancer = Depends(get_load_balancer),
    config: Config = Depends(get_config)
):
    """Fallback route for any other OpenAI-compatible endpoints"""
    # Ensure the path starts with /v1/
    final_path = f"/v1/{path}" if not path.startswith("v1/") else f"/{path}"
    
    return await _forward_request_with_retry(
        request=request,
        path=final_path,
        method=request.method,
        load_balancer=load_balancer,
        config=config
    )
