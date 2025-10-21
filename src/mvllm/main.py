"""
FastAPI application for vLLM Router
"""

import os
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn
from loguru import logger

from mvllm.routes import router

from .config import get_config
from .load_manager import get_load_manager
from . import __version__

# Remove default logging handler
logger.remove()


# Configure logging with Rich console
def setup_logging():
    """Setup Rich-based logging with console and file output"""

    # Create logs directory if it doesn't exist
    logs_dir = "logs"
    os.makedirs(logs_dir, exist_ok=True)

    # Configure uvicorn logging to work with Rich
    # Suppress uvicorn's default logger to avoid conflicts
    import logging

    logging.getLogger("uvicorn").handlers.clear()
    logging.getLogger("uvicorn.access").handlers.clear()
    logging.getLogger("uvicorn.error").handlers.clear()

    # Disable FastAPI logging
    logging.getLogger("fastapi").handlers.clear()
    logging.getLogger("fastapi.access").handlers.clear()
    logging.getLogger("starlette").handlers.clear()

    # Console handler with Rich format - only enabled when --console is used
    if os.getenv("LOG_TO_CONSOLE", "false").lower() == "true":
        # Use Rich handler for console logging
        from rich.logging import RichHandler

        # Configure loguru with Rich handler for console output
        console_handler = RichHandler(rich_tracebacks=True, tracebacks_show_locals=True)
        logger.add(
            console_handler,
            level=os.getenv("LOG_LEVEL", "INFO"),
            format="{message}",
            filter=lambda record: not record["extra"].get("status_update", False),
        )
        logger.info("Console logging enabled")

    # Always enable file logging
    logger.add(
        os.path.join(logs_dir, "mvllm.log"),
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level=os.getenv("LOG_LEVEL", "INFO"),
        rotation="10 MB",
        retention="7 days",
        compression="zip",
        encoding="utf-8",
    )

    # Error log file
    logger.add(
        os.path.join(logs_dir, "mvllm-error.log"),
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level="ERROR",
        rotation="10 MB",
        retention="30 days",
        compression="zip",
        encoding="utf-8",
    )

    # Clean structured log file for analytics
    logger.add(
        os.path.join(logs_dir, "mvllm-structured.log"),
        format="{time:YYYY-MM-DD HH:mm:ss} | {level.name} | {message} | {extra}",
        level=os.getenv("LOG_LEVEL", "INFO"),
        rotation="50 MB",
        retention="7 days",
        compression="zip",
        encoding="utf-8",
    )

    # Log startup status
    if os.getenv("LOG_TO_CONSOLE", "false").lower() == "true":
        logger.info("Console logging enabled")
    else:
        logger.info("Console logging disabled (use --console to enable)")


# Initialize logging - will be called again in main() with proper environment variables
# setup_logging()

# Global variables for services
load_manager = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    global load_manager

    # Startup
    logger.info("Starting vLLM Router...")

    # Initialize configuration
    config = get_config()

    # Initialize load manager
    # Detect if console output is enabled to decide whether to use fullscreen mode
    console_enabled = os.getenv("LOG_TO_CONSOLE", "false").lower() == "true"
    fullscreen_mode = (
        not console_enabled
    )  # Use fullscreen mode when console is disabled

    # Get parameter for whether to display model information
    show_models = os.getenv("SHOW_MODELS", "false").lower() == "true"

    load_manager_instance = get_load_manager(
        fullscreen_mode=fullscreen_mode, show_models=show_models
    )
    await load_manager_instance.start_load_monitor(
        interval=0.5, use_rich=True
    )  # Update load status every 0.5 seconds, use Rich display

    if fullscreen_mode:
        logger.info("vLLM Router running in fullscreen monitor mode (console disabled)")
    else:
        logger.info("vLLM Router running with console output enabled")

    # Update model information for all servers
    logger.info("Fetching model information from all servers...")
    await config.update_all_server_models()
    logger.info("Model information update completed")

    # Start active health check task
    if config.app_config.enable_active_health_check:
        health_check_task = asyncio.create_task(
            active_health_check_loop(config, config.app_config.health_check_interval)
        )
        logger.info(
            f"Active health check started with interval: {config.app_config.health_check_interval}s"
        )
    else:
        health_check_task = None
        logger.info("Active health check disabled")

    # Start config reload task
    config_reload_task = asyncio.create_task(
        config_reload_loop(config, config.app_config.config_reload_interval)
    )
    logger.info(
        f"Config reload task started with interval: {config.app_config.config_reload_interval}s"
    )

    logger.info("vLLM Router started successfully")

    yield

    # Shutdown
    logger.info("Shutting down vLLM Router...")

    # Cancel tasks
    if load_manager_instance:
        await load_manager_instance.stop_load_monitor()

    if health_check_task and not health_check_task.done():
        health_check_task.cancel()
        try:
            await health_check_task
        except asyncio.CancelledError:
            pass

    if config_reload_task and not config_reload_task.done():
        config_reload_task.cancel()
        try:
            await config_reload_task
        except asyncio.CancelledError:
            pass

    logger.info("vLLM Router shutdown complete")


async def active_health_check_loop(config, interval: int):
    """Active health check loop that runs periodically"""
    logger.info(f"Starting active health check loop with interval: {interval}s")

    while True:
        try:
            await asyncio.sleep(interval)

            # Perform health checks on all servers
            health_results = await config.perform_health_checks()

            # Update model information periodically (every 10 health check cycles)
            # This prevents overwhelming the servers with model requests
            model_update_counter = getattr(active_health_check_loop, "counter", 0)
            model_update_counter += 1
            setattr(active_health_check_loop, "counter", model_update_counter)

            if model_update_counter % 10 == 0:  # Update models every 10 cycles
                logger.info("Updating model information during health check cycle...")
                await config.update_all_server_models()

            # Log summary of health check results
            healthy_count = sum(
                1 for is_healthy, _ in health_results.values() if is_healthy
            )
            total_count = len(health_results)

            if total_count > 0:
                logger.info(
                    f"Health check completed: {healthy_count}/{total_count} servers healthy"
                )

                # Log detailed results for unhealthy servers
                for server_url, (is_healthy, response_time) in health_results.items():
                    if not is_healthy:
                        logger.warning(
                            f"Server {server_url} is unhealthy (response_time: {response_time:.2f}s)"
                        )

        except asyncio.CancelledError:
            logger.info("Active health check loop cancelled")
            break
        except Exception as e:
            logger.error(f"Error in active health check loop: {e}")
            await asyncio.sleep(interval)  # Continue even after errors


async def config_reload_loop(config, interval: int):
    """Config reload loop that runs periodically"""
    logger.info(f"Starting config reload loop with interval: {interval}s")

    while True:
        try:
            await asyncio.sleep(interval)

            # Check if configuration needs to be reloaded
            if config.reload_if_needed():
                logger.info("Configuration reloaded successfully")

                # Log new configuration details
                healthy_servers = config.get_healthy_servers()
                total_servers = len(config.servers)
                logger.info(
                    f"Configuration reloaded: {len(healthy_servers)}/{total_servers} servers healthy"
                )

        except asyncio.CancelledError:
            logger.info("Config reload loop cancelled")
            break
        except Exception as e:
            logger.error(f"Error in config reload loop: {e}")
            await asyncio.sleep(interval)  # Continue even after errors


# Create FastAPI application
app = FastAPI(
    title="vLLM Router",
    description="A FastAPI-based load balancer for vLLM servers with OpenAI-compatible API",
    version=__version__,
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routes
app.include_router(router, prefix="/v1")


@app.get("/")
async def root():
    """Root endpoint"""
    return {"service": "vLLM Router", "version": __version__, "status": "running"}


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    config = get_config()
    healthy_servers = config.get_healthy_servers()
    total_servers = len(config.servers)

    # Calculate overall health score
    if total_servers == 0:
        overall_status = "no_servers"
        health_score = 0.0
    else:
        healthy_count = len(healthy_servers)
        health_ratio = healthy_count / total_servers
        health_score = health_ratio

        if health_ratio >= 0.8:
            overall_status = "healthy"
        elif health_ratio >= 0.5:
            overall_status = "degraded"
        else:
            overall_status = "unhealthy"

    # Calculate detailed server information
    server_details = []
    for server in config.servers:
        server_info = {
            "url": server.url,
            "healthy": server.is_healthy,
            "last_check": server.last_check.isoformat() if server.last_check else None,
            "consecutive_failures": server.consecutive_failures,
            "success_rate": server.health_stats.success_rate,
            "avg_response_time": server.health_stats.avg_response_time,
            "last_response_time": server.health_stats.last_response_time,
            "total_checks": server.health_stats.total_checks,
            "supported_models": server.supported_models,
            "models_last_updated": server.models_last_updated.isoformat()
            if server.models_last_updated
            else None,
        }
        server_details.append(server_info)

    return {
        "status": overall_status,
        "health_score": health_score,
        "total_servers": total_servers,
        "healthy_servers": len(healthy_servers),
        "unhealthy_servers": total_servers - len(healthy_servers),
        "servers": server_details,
        "config": {
            "health_check_enabled": config.app_config.enable_active_health_check,
            "health_check_interval": config.app_config.health_check_interval,
            "min_success_rate": config.app_config.health_check_min_success_rate,
            "max_response_time": config.app_config.health_check_max_response_time,
        },
    }


@app.get("/load-stats")
async def load_stats():
    """Load statistics endpoint"""
    load_manager = get_load_manager()
    stats = load_manager.get_load_stats()

    # Format output for better readability
    return {
        "servers": [
            {
                "url": server_url,
                "current_load": load_info["current_load"],
                "max_capacity": load_info["max_capacity"],
                "available_capacity": load_info["available_capacity"],
                "utilization_percent": load_info["utilization"],
                "status": load_info["status"],
                "last_updated": load_info["last_updated"],
                "detailed_metrics": load_info["detailed_metrics"],
            }
            for server_url, load_info in stats["server_loads"].items()
        ],
        "summary": {
            "total_servers": stats["total_servers"],
            "healthy_servers": stats["healthy_servers"],
            "total_active_load": stats["summary"]["total_active_load"],
            "total_capacity": stats["summary"]["total_capacity"],
            "overall_utilization_percent": stats["summary"]["overall_utilization"],
        },
    }


@app.get("/server-models")
async def server_models():
    """Get all servers and their supported models"""
    config = get_config()

    # Update model information if needed (force refresh)
    await config.update_all_server_models()

    server_models = {}
    for server in config.servers:
        server_models[server.url] = {
            "supported_models": server.supported_models,
            "models_last_updated": server.models_last_updated.isoformat()
            if server.models_last_updated
            else None,
            "healthy": server.is_healthy,
        }

    return {
        "servers": server_models,
        "total_servers": len(config.servers),
        "healthy_servers": len(config.get_healthy_servers()),
    }


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """HTTP exception handler"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "message": exc.detail,
                "type": "http_error",
                "code": exc.status_code,
            }
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """General exception handler"""
    logger.bind(
        path=request.url.path,
        method=request.method,
        error_type=type(exc).__name__,
        error_message=str(exc),
        status="unhandled_exception",
    ).error("Unhandled exception occurred", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "message": "Internal server error",
                "type": "internal_error",
                "code": 500,
            }
        },
    )


def main():
    """Main entry point"""
    # Setup logging with current environment variables
    setup_logging()

    # Parse command line arguments for uvicorn
    import sys

    host = "0.0.0.0"
    port = 8888
    reload = False

    # Parse sys.argv for uvicorn parameters
    i = 0
    while i < len(sys.argv):
        if sys.argv[i] == "--host" and i + 1 < len(sys.argv):
            host = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "--port" and i + 1 < len(sys.argv):
            port = int(sys.argv[i + 1])
            i += 2
        elif sys.argv[i] == "--reload":
            reload = True
            i += 1
        else:
            i += 1

    logger.info(f"Starting server on {host}:{port}")

    uvicorn.run(
        app,
        host=host,
        port=port,
        reload=reload,
        log_config=None,  # Disable uvicorn's logging
        log_level="critical",  # Set to highest level to suppress log output
        access_log=False,  # Disable access logs
    )


if __name__ == "__main__":
    main()
