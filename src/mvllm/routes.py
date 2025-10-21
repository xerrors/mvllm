import asyncio
import httpx
import random
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import StreamingResponse, JSONResponse
from typing import Union, List
from loguru import logger
from .config import Config, get_config
from .load_manager import LoadManager, get_load_manager

__all__ = [
    "router",
]

router = APIRouter()


async def _select_optimal_server(
    config: Config, load_manager: LoadManager, model: str = None
) -> str:
    """Select the healthy server with the lowest current load, optionally filtering servers that support the specified model"""
    if model:
        # If a model is specified, only select healthy servers that support it
        healthy_servers = config.get_healthy_servers_supporting_model(model)
        if not healthy_servers:
            raise HTTPException(
                status_code=503,
                detail=f"No healthy servers available that support model: {model}",
            )
    else:
        # If no model is specified, select all healthy servers
        healthy_servers = config.get_healthy_servers()

    if not healthy_servers:
        if model:
            raise HTTPException(
                status_code=503,
                detail=f"No servers available that support model: {model}",
            )
        else:
            raise HTTPException(status_code=503, detail="No healthy servers available")

    # Get real-time load data
    load_stats = load_manager.get_load_stats()

    # Calculate a composite score for each server (load + available capacity)
    candidates_under_threshold: List = []  # Store servers with score < 0.5
    best_servers: List = []  # Store servers with the same score (fallback selection)
    best_score = float("inf")

    for server in healthy_servers:
        server_load_info = load_stats["server_loads"].get(server.url, {})
        detailed_metrics = server_load_info.get("detailed_metrics", {})
        max_capacity = server_load_info.get("max_capacity", 3)

        # Get detailed load data and capacity
        running = detailed_metrics.get("num_requests_running", 0)
        waiting = detailed_metrics.get("num_requests_waiting", 0)
        capacity = max_capacity

        # Calculate relative load (considering server capacity)
        # Composite score: Running requests have higher weight, divide by capacity to ensure fair comparison
        if capacity > 0:
            score = (running + waiting * 0.5) / capacity
        else:
            score = float("inf")  # Servers with zero capacity should not be selected

        # Collect servers with score < 0.5
        if score < 0.5:
            candidates_under_threshold.append(server)

        # Also record servers with the best score as fallback
        if score < best_score:
            best_score = score
            best_servers = [
                server
            ]  # Reset list to only include the current best server
        elif score == best_score:
            best_servers.append(server)  # Add servers with the same score

    # Prioritize servers with score < 0.5
    if candidates_under_threshold:
        selected_server = random.choice(candidates_under_threshold)
        selected_metrics = load_stats["server_loads"][selected_server.url][
            "detailed_metrics"
        ]
        logger.info(
            f"Selected server {selected_server.url} from {len(candidates_under_threshold)} candidates under threshold (score < 0.5) - Running: {selected_metrics['num_requests_running']}, Waiting: {selected_metrics['num_requests_waiting']}"
        )
        return selected_server.url

    # If no servers with score < 0.5, select the one with the lowest score
    if best_servers:
        selected_server = random.choice(best_servers)
        selected_metrics = load_stats["server_loads"][selected_server.url][
            "detailed_metrics"
        ]
        logger.info(
            f"Selected server {selected_server.url} from {len(best_servers)} candidates with best score {best_score} - Running: {selected_metrics['num_requests_running']}, Waiting: {selected_metrics['num_requests_waiting']}"
        )
        return selected_server.url

    # Should theoretically never reach here
    selected = healthy_servers[0]
    logger.info(f"Randomly selected server {selected.url}")
    return selected.url


async def _extract_model_from_request(request: Request) -> str:
    """Extract model name from the request"""
    try:
        # For chat completions and regular completions requests, the model is typically in the request body
        if request.method in ["POST"] and request.url.path in [
            "/v1/chat/completions",
            "/v1/completions",
        ]:
            # Read the request body
            body = await request.body()
            if not body:
                return None

            import json

            try:
                request_data = json.loads(body)
                model = request_data.get("model")
                return model
            except (json.JSONDecodeError, AttributeError):
                pass

        # Get model from query parameters (if applicable)
        model = request.query_params.get("model")
        return model

    except Exception:
        return None


async def _forward_request_with_retry(
    request: Request, path: str, method: str, config: Config, load_manager: LoadManager
) -> Union[JSONResponse, StreamingResponse]:
    """
    Forward request directly to the optimal server with retry logic
    """
    # Get headers
    headers = dict(request.headers)
    headers.pop("host", None)  # Avoid header conflicts

    # Extract model information
    model = await _extract_model_from_request(request)

    retries = 0
    max_retries = config.app_config.max_retries

    while retries <= max_retries:
        try:
            # Select the optimal server (filtered by model)
            server_url = await _select_optimal_server(config, load_manager, model)
            target_url = f"{server_url}{path}"

            model_info = f" (model: {model})" if model else ""
            logger.info(
                f"Forwarding {method} {path} to {target_url}{model_info} (attempt {retries + 1}/{max_retries + 1})"
            )

            # Forward the request
            async with httpx.AsyncClient(
                timeout=config.app_config.request_timeout
            ) as client:
                # For requests that need a body, we need to re-read the request body
                if method in ["POST", "PUT", "PATCH"]:
                    body = await request.body()
                    response = await client.request(
                        method=method, url=target_url, content=body, headers=headers
                    )
                else:
                    response = await client.request(
                        method=method, url=target_url, headers=headers
                    )

            response.raise_for_status()  # Check response status

            # Handle successful response
            if response.headers.get("content-type", "").startswith("text/event-stream"):
                # Streaming response
                async def stream_response():
                    try:
                        async for chunk in response.aiter_bytes():
                            yield chunk
                    except Exception as e:
                        logger.error(f"Error streaming response from {server_url}: {e}")
                    finally:
                        logger.info(
                            f"Stream completed for {method} {path} from {server_url}"
                        )

                return StreamingResponse(
                    stream_response(),
                    status_code=response.status_code,
                    headers=dict(response.headers),
                )
            else:
                # JSON response
                logger.info(
                    f"Request {method} {path} completed successfully on {server_url}{model_info}"
                )
                return JSONResponse(
                    content=response.json(),
                    status_code=response.status_code,
                    headers=dict(response.headers),
                )

        except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPStatusError) as e:
            logger.warning(f"Request failed on {server_url}: {e}")

            # Mark the server as unhealthy
            config.update_server_health(server_url, False)

            if retries >= max_retries:
                logger.error(
                    f"Request {method} {path} exceeded max retry count ({max_retries})"
                )
                raise HTTPException(
                    status_code=502, detail="Bad gateway - max retries exceeded"
                )

            retries += 1
            logger.info(f"Retrying request (attempt {retries}/{max_retries})")
            # Wait before retrying
            await asyncio.sleep(0.1)

        except Exception as e:
            logger.error(f"Unexpected error for request {method} {path}: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    # Should theoretically not reach here
    raise HTTPException(
        status_code=500,
        detail="Internal server error: Unexpected flow in request forwarding",
    )


@router.post("/chat/completions")
async def chat_completions(
    request: Request,
    config: Config = Depends(get_config),
    load_manager: LoadManager = Depends(get_load_manager),
):
    """OpenAI-compatible chat completions endpoint"""
    return await _forward_request_with_retry(
        request=request,
        path="/v1/chat/completions",
        method="POST",
        config=config,
        load_manager=load_manager,
    )


@router.post("/completions")
async def completions(
    request: Request,
    config: Config = Depends(get_config),
    load_manager: LoadManager = Depends(get_load_manager),
):
    """OpenAI-compatible completions endpoint"""
    return await _forward_request_with_retry(
        request=request,
        path="/v1/completions",
        method="POST",
        config=config,
        load_manager=load_manager,
    )


@router.get("/models")
async def models(config: Config = Depends(get_config)):
    """OpenAI-compatible models endpoint - returns all available models from all servers"""
    try:
        # Update model information for all servers
        await config.update_all_server_models()

        # Collect all models supported by servers
        all_models = set()
        model_details = []

        for server in config.servers:
            if server.is_healthy and server.supported_models:
                for model_name in server.supported_models:
                    if model_name not in all_models:
                        all_models.add(model_name)
                        model_details.append(
                            {
                                "id": model_name,
                                "object": "model",
                                "created": int(server.models_last_updated.timestamp())
                                if server.models_last_updated
                                else 0,
                                "owned_by": "vllm-router",
                                "permission": [],
                                "root": model_name,
                                "parent": None,
                            }
                        )

        # If no models are found, return a default response
        if not model_details:
            model_details = [
                {
                    "id": "no-models-available",
                    "object": "model",
                    "created": 0,
                    "owned_by": "vllm-router",
                    "permission": [],
                    "root": "no-models-available",
                    "parent": None,
                }
            ]

        return {"object": "list", "data": model_details}

    except Exception as e:
        logger.error(f"Error getting models: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error retrieving models: {str(e)}"
        )


@router.post("/embeddings")
async def embeddings(
    request: Request,
    config: Config = Depends(get_config),
    load_manager: LoadManager = Depends(get_load_manager),
):
    """OpenAI-compatible embeddings endpoint"""
    return await _forward_request_with_retry(
        request=request,
        path="/v1/embeddings",
        method="POST",
        config=config,
        load_manager=load_manager,
    )


@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def openai_fallback(
    path: str,
    request: Request,
    config: Config = Depends(get_config),
    load_manager: LoadManager = Depends(get_load_manager),
):
    """Fallback route for any other OpenAI-compatible endpoints"""
    # Ensure the path starts with /v1/
    final_path = f"/v1/{path}" if not path.startswith("v1/") else f"/{path}"

    return await _forward_request_with_retry(
        request=request,
        path=final_path,
        method=request.method,
        config=config,
        load_manager=load_manager,
    )
