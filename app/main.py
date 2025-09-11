"""
FastAPI application for vLLM Router
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn

from .config import Config
from .health_checker import HealthChecker
from .config_reloader import ConfigReloader
from .routes import router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global variables for services
config: Config = None
health_checker: HealthChecker = None
config_reloader: ConfigReloader = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    global config, health_checker, config_reloader
    
    # Startup
    logger.info("Starting vLLM Router...")
    
    # Initialize configuration
    config = Config()
    
    # Initialize and start health checker
    health_checker = HealthChecker(config)
    await health_checker.start()
    
    # Initialize and start config reloader
    config_reloader = ConfigReloader(config)
    await config_reloader.start()
    
    logger.info("vLLM Router started successfully")
    
    yield
    
    # Shutdown
    logger.info("Shutting down vLLM Router...")
    
    if health_checker:
        await health_checker.stop()
    
    if config_reloader:
        await config_reloader.stop()
    
    logger.info("vLLM Router shutdown complete")

# Create FastAPI application
app = FastAPI(
    title="vLLM Router",
    description="A FastAPI-based load balancer for vLLM servers with OpenAI-compatible API",
    version="0.1.0",
    lifespan=lifespan
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
    return {
        "service": "vLLM Router",
        "version": "0.1.0",
        "status": "running"
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    healthy_servers = config.get_healthy_servers()
    total_servers = len(config.servers)
    
    return {
        "status": "healthy" if len(healthy_servers) > 0 else "degraded",
        "total_servers": total_servers,
        "healthy_servers": len(healthy_servers),
        "servers": [
            {
                "url": server.url,
                "healthy": server.is_healthy,
                "weight": server.weight,
                "last_check": server.last_check.isoformat() if server.last_check else None
            }
            for server in config.servers
        ]
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
                "code": exc.status_code
            }
        }
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """General exception handler"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "message": "Internal server error",
                "type": "internal_error",
                "code": 500
            }
        }
    )

def main():
    """Main entry point"""
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8888,
        reload=True,
        log_level="info"
    )

if __name__ == "__main__":
    main()