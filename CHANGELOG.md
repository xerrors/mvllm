# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2025-10-21

### Added
- Initial release of vLLM Router
- FastAPI-based load balancer for vLLM servers
- OpenAI-compatible API endpoints
  - `/v1/chat/completions` - Chat completions
  - `/v1/completions` - Text completions
  - `/v1/models` - List available models
  - `/v1/embeddings` - Embeddings support
- Intelligent load balancing algorithm
  - Real-time metrics from vLLM `/metrics` endpoint
  - Smart scoring: `(running + waiting * 0.5) / capacity`
  - Priority selection for servers with load < 50%
  - Automatic failover and retry logic
- Model-aware routing
  - Automatic model discovery from servers
  - Route requests to servers supporting specific models
  - Consolidated model listing across all servers
- Health monitoring system
  - Active health checks with configurable intervals
  - Passive health tracking based on request success/failure
  - Auto-recovery for temporarily failed servers
  - Detailed health statistics (success rate, response time)
- Real-time monitoring dashboard
  - Rich terminal UI with live updates
  - Fullscreen mode for production monitoring
  - Console mode for development/debugging
  - Per-server metrics display (running, waiting, capacity, utilization)
  - Optional model information display
- CLI interface powered by Typer
  - `mvllm run` - Start the router
  - `mvllm check-config` - Validate configuration
  - `mvllm version` - Show version information
  - Support for custom host, port, and config file
- Configuration management
  - TOML-based configuration file
  - Hot-reload of configuration changes
  - Environment variable support
  - Flexible server settings (max concurrent requests, timeouts, etc.)
- Comprehensive logging
  - Loguru-based structured logging
  - Separate log files for general logs, errors, and structured analytics
  - Rich console output with color and formatting
  - Configurable log levels
- API endpoints for monitoring
  - `/health` - Overall system health with detailed server status
  - `/load-stats` - Real-time load statistics
  - `/server-models` - Server and model information
  - `/` - Root endpoint with version info

### Documentation
- English and Chinese README files
- Comprehensive API documentation
- Configuration examples
- Contributing guidelines
- MIT License

### Infrastructure
- Modern Python packaging with `pyproject.toml`
- Hatchling build backend
- Support for Python 3.10+
- Async/await throughout for high performance
- Type hints for better code quality

[0.1.0]: https://github.com/xerrors/mvllm/releases/tag/v0.1.0
