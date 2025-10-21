"""
Command line interface for vLLM Router using Typer
"""

import os
import sys
import typer
from .main import main as app_main
from .config import get_config
from . import __version__

app = typer.Typer(
    name="mvllm",
    help="A FastAPI-based load balancer for vLLM servers with real-time load monitoring",
    add_completion=False,
)


@app.command()
def run(
    console: bool = typer.Option(
        False, "--console", "-c", help="Enable console logging output"
    ),
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="Host to bind to"),
    port: int = typer.Option(8888, "--port", "-p", help="Port to bind to"),
    config: str = typer.Option(
        "servers.toml", "--config", help="Path to configuration file"
    ),
    reload: bool = typer.Option(
        False, "--reload", help="Enable auto-reload for development"
    ),
    log_level: str = typer.Option(
        "INFO", "--log-level", help="Logging level (DEBUG, INFO, WARNING, ERROR)"
    ),
    model: bool = typer.Option(
        False, "--model", "-m", help="Show model information in the server display"
    ),
):
    """Run the vLLM Router server"""

    # Set environment variables based on CLI options
    os.environ["LOG_TO_CONSOLE"] = str(console).lower()
    os.environ["LOG_LEVEL"] = log_level
    os.environ["CONFIG_PATH"] = config
    os.environ["SHOW_MODELS"] = str(model).lower()

    # Set uvicorn arguments
    sys.argv = [
        "mvllm",
        "--host",
        host,
        "--port",
        str(port),
    ]

    if reload:
        sys.argv.extend(["--reload"])

    # Run the main application
    app_main()


@app.command()
def check_config(
    config: str = typer.Option(
        "servers.toml", "--config", help="Path to configuration file"
    ),
):
    """Check configuration file syntax and server connectivity"""
    os.environ["CONFIG_PATH"] = config
    os.environ["LOG_TO_CONSOLE"] = "true"

    try:
        config_instance = get_config()
        print("✅ Configuration loaded successfully")
        print(f"   Total servers: {len(config_instance.servers)}")
        print(f"   Healthy servers: {len(config_instance.get_healthy_servers())}")

        for server in config_instance.servers:
            status = "✅" if server.is_healthy else "❌"
            print(
                f"   {status} {server.url} (max_concurrent: {server.max_concurrent_requests})"
            )

    except Exception as e:
        print(f"❌ Configuration error: {e}")
        raise typer.Exit(1)


@app.command()
def version():
    """Show version information"""
    print(f"vLLM Router v{__version__}")
    print("Real-time load balancing for vLLM servers")


if __name__ == "__main__":
    app()
