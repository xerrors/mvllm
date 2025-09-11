"""
OpenAI-compatible API routes for vLLM Router
"""

import httpx
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import StreamingResponse, JSONResponse
from typing import Dict, Any, Optional, Union
import logging
import json
from .config import Config, get_config
from .load_balancer import LoadBalancer, get_load_balancer

logger = logging.getLogger(__name__)

router = APIRouter()

async def get_config() -> Config:
    """Get configuration instance"""
    from .config import get_config as get_global_config
    return get_global_config()

async def get_load_balancer() -> LoadBalancer:
    """Get load balancer instance"""
    from .load_balancer import get_load_balancer as get_global_load_balancer
    return get_global_load_balancer()

async def forward_request(
    request: Request,
    target_url: str,
    path: str,
    method: str
) -> Union[JSONResponse, StreamingResponse]:
    """Forward request to target server"""
    config = await get_config()
    
    # Build target URL
    target = f"{target_url}{path}"
    
    # Get request body
    body = await request.body()
    
    # Get headers
    headers = dict(request.headers)
    # Remove host header as it will cause issues
    headers.pop('host', None)
    
    logger.info(f"Forwarding {method} request to {target}")
    
    try:
        async with httpx.AsyncClient(timeout=config.app_config.request_timeout) as client:
            # Make the request
            response = await client.request(
                method=method,
                url=target,
                content=body,
                headers=headers
            )
            
            # Handle different response types
            if response.headers.get('content-type', '').startswith('text/event-stream'):
                # Streaming response
                async def stream_response():
                    async for chunk in response.aiter_bytes():
                        yield chunk
                
                return StreamingResponse(
                    stream_response(),
                    status_code=response.status_code,
                    headers=dict(response.headers)
                )
            else:
                # Regular JSON response
                response_data = response.json()
                return JSONResponse(
                    content=response_data,
                    status_code=response.status_code,
                    headers=dict(response.headers)
                )
    
    except httpx.TimeoutException:
        logger.error(f"Request to {target} timed out")
        raise HTTPException(status_code=504, detail="Gateway timeout")
    except httpx.ConnectError:
        logger.error(f"Failed to connect to {target}")
        raise HTTPException(status_code=502, detail="Bad gateway")
    except Exception as e:
        logger.error(f"Error forwarding request to {target}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/chat/completions")
async def chat_completions(
    request: Request,
    load_balancer: LoadBalancer = Depends(get_load_balancer)
):
    """OpenAI-compatible chat completions endpoint"""
    # Get a server from load balancer
    server = load_balancer.get_server()
    
    if not server:
        raise HTTPException(status_code=503, detail="No healthy servers available")
    
    try:
        # Forward request to selected server
        return await forward_request(
            request=request,
            target_url=server.url,
            path="/v1/chat/completions",
            method="POST"
        )
    except HTTPException:
        # Mark server as unhealthy and retry with another server
        from .main import config
        config.update_server_health(server.url, False)
        
        # Try another server
        retry_server = load_balancer.get_server()
        if retry_server:
            logger.info(f"Retrying with server: {retry_server.url}")
            return await forward_request(
                request=request,
                target_url=retry_server.url,
                path="/v1/chat/completions",
                method="POST"
            )
        else:
            raise HTTPException(status_code=503, detail="No healthy servers available")

@router.post("/completions")
async def completions(
    request: Request,
    load_balancer: LoadBalancer = Depends(get_load_balancer)
):
    """OpenAI-compatible completions endpoint"""
    server = load_balancer.get_server()
    
    if not server:
        raise HTTPException(status_code=503, detail="No healthy servers available")
    
    try:
        return await forward_request(
            request=request,
            target_url=server.url,
            path="/v1/completions",
            method="POST"
        )
    except HTTPException:
        # Mark server as unhealthy and retry
        from .main import config
        config.update_server_health(server.url, False)
        
        retry_server = load_balancer.get_server()
        if retry_server:
            return await forward_request(
                request=request,
                target_url=retry_server.url,
                path="/v1/completions",
                method="POST"
            )
        else:
            raise HTTPException(status_code=503, detail="No healthy servers available")

@router.get("/models")
async def models(
    request: Request,
    load_balancer: LoadBalancer = Depends(get_load_balancer)
):
    """OpenAI-compatible models endpoint"""
    server = load_balancer.get_server()
    
    if not server:
        raise HTTPException(status_code=503, detail="No healthy servers available")
    
    return await forward_request(
        request=request,
        target_url=server.url,
        path="/v1/models",
        method="GET"
    )

@router.post("/embeddings")
async def embeddings(
    request: Request,
    load_balancer: LoadBalancer = Depends(get_load_balancer)
):
    """OpenAI-compatible embeddings endpoint"""
    server = load_balancer.get_server()
    
    if not server:
        raise HTTPException(status_code=503, detail="No healthy servers available")
    
    return await forward_request(
        request=request,
        target_url=server.url,
        path="/v1/embeddings",
        method="POST"
    )

# Generic fallback route for any other OpenAI-compatible endpoints
@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def openai_fallback(
    path: str,
    request: Request,
    load_balancer: LoadBalancer = Depends(get_load_balancer)
):
    """Fallback route for any other OpenAI-compatible endpoints"""
    server = load_balancer.get_server()
    
    if not server:
        raise HTTPException(status_code=503, detail="No healthy servers available")
    
    return await forward_request(
        request=request,
        target_url=server.url,
        path=f"/v1/{path}",
        method=request.method
    )