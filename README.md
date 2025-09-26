# vLLM Router

<div align="center">

**🚀 Enterprise-Grade Load Balancer for Distributed vLLM Servers**

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green.svg)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Stars](https://img.shields.io/github/stars/xerrors/vllm-router?style=social)](https://github.com/xerrors/vllm-router)

**Solve GPU fragmentation with intelligent load balancing across multiple vLLM instances**

[Quick Start](#quick-start) • [Features](#key-features) • [Architecture](#architecture) • [Documentation](#documentation)

</div>

---

## 🎯 The Problem: GPU Fragmentation in LLM Deployment

Modern LLMs like Llama 3.1-8B require significant GPU resources, but often organizations face:

- **Scattered GPU Resources**: Multiple machines with individual GPUs that can't be combined
- **Resource Underutilization**: Idle GPUs while others are overloaded
- **Management Complexity**: Manual coordination across multiple vLLM instances
- **Availability Challenges**: Downtime when individual nodes need maintenance

**vLLM Router solves these challenges** by providing a unified entry point that intelligently distributes requests across your vLLM fleet.

---

## 🚀 Key Features

### 🔀 Intelligent Multi-Endpoint Load Balancing
- **Real-time Metrics**: Direct integration with vLLM `/metrics` endpoints
- **Capacity-Aware Routing**: Considers both current load and server capacity
- **Weighted Distribution**: Smart algorithm: `(running * 3 + waiting) / capacity`
- **Zero Queue Bottlenecks**: Direct request forwarding without intermediate queues

### 📊 Advanced Monitoring & Visualization
- **Live Dashboard**: Real-time load monitoring with Rich console interface
- **Fullscreen Mode**: Dedicated monitoring view when console logging is disabled
- **Detailed Metrics**: Running requests, waiting queue, GPU cache usage, file descriptors
- **Health Status**: Automatic health checks and failover detection

### ⚡ High Availability & Reliability
- **Automatic Failover**: Instant detection and removal of unhealthy servers
- **Circuit Breaker**: Prevent cascading failures with intelligent retry logic
- **Graceful Degradation**: Continue serving requests even during partial outages
- **Configurable Timeouts**: Fine-tuned timeout and retry policies

### 🔧 Configuration Management
- **Hot Reload**: Update configuration without service interruption
- **TOML Configuration**: Human-readable configuration files
- **Environment Variables**: Flexible deployment options
- **Dynamic Scaling**: Add/remove servers without restart

### 🌐 OpenAI API Compatibility
- **Seamless Integration**: Drop-in replacement for OpenAI API endpoints
- **Complete Coverage**: Chat completions, text completions, embeddings, models listing
- **Client Agnostic**: Works with any OpenAI-compatible client library

---

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Client Applications                      │
├─────────────────────────────────────────────────────────────┤
│                  vLLM Router (Load Balancer)                  │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │   Load Manager  │  │  Health Monitor │  │ Config Manager │ │
│  │  - Real-time    │  │  - Auto-healing │  │  - Hot reload   │ │
│  │  metrics       │  │  - Failover     │  │  - Validation   │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
├─────────────────────────────────────────────────────────────┤
│                    vLLM Server Cluster                        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐           │
│  │ vLLM Node 1 │  │ vLLM Node 2 │  │ vLLM Node N │           │
│  │ GPU: 1xRTX │  │ GPU: 2x4090 │  │ GPU: 1xA100 │           │
│  │ Llama-3.1-8B│  │ Llama-3.1-8B│  │ Mixtral-8x7B│           │
│  └─────────────┘  └─────────────┘  └─────────────┘           │
└─────────────────────────────────────────────────────────────┘
```

### Core Components

1. **Load Manager**: Real-time load monitoring and server selection
2. **Health Monitor**: Continuous health checks and automatic failover
3. **Config Manager**: Dynamic configuration management and validation
4. **Request Router**: Intelligent request distribution with retry logic

---

## 🚀 Quick Start

### Prerequisites

- Python 3.8+
- Multiple vLLM servers running on different machines
- Network connectivity between router and vLLM servers

### Installation

```bash
# Clone the repository
git clone https://github.com/xerrors/vllm-router.git
cd vllm-router

# Install dependencies
uv sync
```

### Configuration

Create your server configuration:

```bash
cp servers.example.toml servers.toml
```

Edit `servers.toml` to define your vLLM cluster:

```toml
[servers]
servers = [
    { url = "http://gpu-server-1:8081", max_concurrent_requests = 3 },
    { url = "http://gpu-server-2:8088", max_concurrent_requests = 5 },
    { url = "http://gpu-server-3:8089", max_concurrent_requests = 4 },
]

[config]
health_check_interval = 10
config_reload_interval = 30
request_timeout = 120
health_check_timeout = 5
max_retries = 3
```

### Running the Router

#### Production Mode (Fullscreen Monitoring)
```bash
# Dedicated monitoring view, no console logs
vllm-router run
```

#### Development Mode (Console Logging)
```bash
# Console output mixed with monitoring
vllm-router run --console
```

#### Advanced Options
```bash
# Custom host and port
vllm-router run --host 0.0.0.0 --port 8888

# Auto-reload for development
vllm-router run --reload --console

# Custom configuration
vllm-router run --config production-servers.toml
```

---

## 📡 API Endpoints

### OpenAI Compatible Endpoints

All endpoints are fully compatible with OpenAI API specification:

```bash
# Chat completions
POST /v1/chat/completions

# Text completions
POST /v1/completions

# Model listing
GET /v1/models

# Embeddings
POST /v1/embeddings
```

### Management & Monitoring Endpoints

```bash
# Service information
GET /

# Health status and cluster statistics
GET /health

# Real-time load metrics and utilization
GET /load-stats
```

---

## 💻 Usage Examples

### Chat Completions

```bash
curl -X POST http://localhost:8888/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama3.1:8b",
    "messages": [
      {"role": "system", "content": "You are a helpful assistant."},
      {"role": "user", "content": "Explain quantum computing in simple terms."}
    ],
    "temperature": 0.7,
    "max_tokens": 500
  }'
```

### Load Statistics

```bash
curl -s http://localhost:8888/load-stats | jq '.'
```

**Response:**
```json
{
  "servers": [
    {
      "url": "http://gpu-server-1:8081",
      "current_load": 2,
      "max_capacity": 3,
      "available_capacity": 1,
      "utilization_percent": 66.7,
      "status": true,
      "detailed_metrics": {
        "num_requests_running": 2,
        "num_requests_waiting": 0,
        "gpu_cache_usage_perc": 78.5,
        "process_max_fds": 65535
      }
    }
  ],
  "summary": {
    "total_servers": 3,
    "healthy_servers": 3,
    "total_active_load": 5,
    "total_capacity": 12,
    "overall_utilization_percent": 41.7
  }
}
```

---

## 🐳 Deployment Options

### Docker Deployment

```bash
# Build the image
docker build -t vllm-router .

# Production run with monitoring
docker run -d \
  --name vllm-router \
  -p 8888:8888 \
  -v $(pwd)/servers.toml:/app/servers.toml \
  vllm-router

# Development run with console
docker run -d \
  --name vllm-router \
  -p 8888:8888 \
  -v $(pwd)/servers.toml:/app/servers.toml \
  -e LOG_TO_CONSOLE=true \
  vllm-router run --console
```

### Docker Compose

```yaml
version: '3.8'
services:
  vllm-router:
    build: .
    ports:
      - "8888:8888"
    volumes:
      - ./servers.toml:/app/servers.toml
    environment:
      - LOG_LEVEL=INFO
    depends_on:
      - vllm-server-1
      - vllm-server-2

  vllm-server-1:
    image: vllm/vllm-openai:latest
    # ... vLLM server configuration ...

  vllm-server-2:
    image: vllm/vllm-openai:latest
    # ... vLLM server configuration ...
```

### Kubernetes Deployment

See `k8s/` directory for complete Kubernetes deployment examples including:

- Helm charts for easy deployment
- Horizontal Pod Autoscaler configuration
- Service mesh integration examples
- Multi-region deployment strategies

---

## 🔧 Configuration

### Server Configuration

```toml
[servers]
servers = [
    # Each server can have different capacities
    { url = "http://server1:8081", max_concurrent_requests = 3 },
    { url = "http://server2:8088", max_concurrent_requests = 8 },
    { url = "http://server3:8089", max_concurrent_requests = 5 },
]

[config]
# Health check settings
health_check_interval = 10          # Check every 10 seconds
health_check_timeout = 5             # 5 second timeout
health_check_min_success_rate = 0.8 # 80% success rate required
health_check_max_response_time = 2.0 # Max 2 second response time

# Configuration management
config_reload_interval = 30          # Check for config changes every 30 seconds
enable_active_health_check = true    # Enable active health monitoring

# Request handling
request_timeout = 120                # 2 minute timeout
max_retries = 3                     # Retry failed requests up to 3 times
retry_delay = 0.1                   # 100ms delay between retries
```

### Environment Variables

```bash
# Basic configuration
CONFIG_PATH=/path/to/servers.toml    # Configuration file path
LOG_LEVEL=INFO                       # Logging level (DEBUG, INFO, WARNING, ERROR)
LOG_TO_CONSOLE=false                 # Enable console logging
HOST=0.0.0.0                        # Bind host
PORT=8888                           # Bind port

# Advanced settings
HEALTH_CHECK_INTERVAL=10             # Health check interval in seconds
CONFIG_RELOAD_INTERVAL=30            # Config reload interval in seconds
REQUEST_TIMEOUT=120                  # Request timeout in seconds
```

---

## 📊 Monitoring & Observability

### Real-time Monitoring

The router provides comprehensive monitoring capabilities:

**Fullscreen Mode** (when `LOG_TO_CONSOLE=false`):
- Dedicated monitoring interface
- Real-time load statistics
- Server health visualization
- Clean, professional display

**Console Mode** (when `LOG_TO_CONSOLE=true`):
- Mixed console logs and monitoring
- Traditional logging experience
- Development-friendly output

### Metrics Collection

- **vLLM Integration**: Direct metrics from `/metrics` endpoints
- **Request Tracking**: Success rates, latency, error distribution
- **Resource Monitoring**: GPU usage, memory, file descriptors
- **Health Status**: Server availability, response times, success rates

### Logging

```bash
# Console output (when enabled)
LOG_TO_CONSOLE=true vllm-router run

# File logging (always enabled)
logs/vllm-router.log          # General application logs
logs/vllm-router-error.log    # Error logs only
logs/vllm-router-structured.log # Machine-readable logs
```

---

## ⚡ Performance Tuning

### Load Balancing Optimization

The intelligent load balancing algorithm considers:

```python
# Score calculation: (running * 3 + waiting * 1) / capacity
# Lower score = better candidate for next request
```

**Tuning Recommendations**:
- **High-Performance Clusters**: Increase `max_concurrent_requests` on powerful nodes
- **Mixed Environments**: Set lower capacities for older/less powerful GPUs
- **Stability Focus**: Reduce `max_retries` and increase `health_check_interval`

### Configuration Optimization

```toml
# High-throughput configuration
[config]
health_check_interval = 5           # Frequent health checks
request_timeout = 60                # Lower timeouts for faster failover
max_retries = 2                     # Fewer retries for faster response

# High-reliability configuration
[config]
health_check_interval = 15          # Less frequent checks
request_timeout = 180               # Higher timeouts for complex models
max_retries = 5                     # More retries for reliability
```

### Scaling Strategies

- **Horizontal Scaling**: Add more vLLM servers to increase throughput
- **Vertical Scaling**: Increase `max_concurrent_requests` on existing servers
- **Geographic Distribution**: Deploy routers closer to user regions
- **Multi-Tier Architecture**: Separate routers for different model types/sizes

---

## 🛠️ Development

### Setup Development Environment

```bash
# Clone and install
git clone https://github.com/xerrors/vllm-router.git
cd vllm-router
uv sync

# Install development dependencies
uv add --dev pytest pytest-asyncio httpx black isort flake8

# Run tests
uv run pytest

# Code quality checks
black --check app/
isort --check-only app/
flake8 app/
```

### Running Tests

```bash
# All tests
uv run pytest

# With coverage
uv run pytest --cov=app --cov-report=html

# Specific test categories
uv run pytest tests/test_load_balancing.py
uv run pytest tests/test_health_monitoring.py
```

### Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

## 🏛️ Production Best Practices

### High Availability Deployment

1. **Multiple Router Instances**: Use a load balancer in front of multiple vLLM Router instances
2. **Health Monitoring**: Implement external health checks with automatic failover
3. **Database Backing**: Store configuration and metrics in a database for persistence
4. **Alerting**: Set up alerts for high error rates or server unavailability

### Security Considerations

```bash
# Production security settings
export LOG_LEVEL=WARNING               # Reduce log verbosity
export REQUEST_TIMEOUT=60              # Lower timeout for security
export HEALTH_CHECK_INTERVAL=5         # Frequent health checks
# Enable HTTPS (recommended)
# Configure firewall rules
# Implement authentication/authorization
```

### Monitoring Stack Integration

- **Prometheus**: Export metrics for monitoring
- **Grafana**: Create dashboards for load and performance visualization
- **AlertManager**: Set up intelligent alerting
- **ELK Stack**: Centralized logging and analysis

---

## 🤝 Community & Support

### Getting Help

- 📖 **Documentation**: [README.md](README.md), [USAGE.md](USAGE.md)
- 🐛 **Bug Reports**: [GitHub Issues](https://github.com/xerrors/vllm-router/issues)
- 💬 **Discussions**: [GitHub Discussions](https://github.com/xerrors/vllm-router/discussions)
- 📧 **Email Support**: Create an issue with the "question" label

### Contributing

We encourage contributions from the community! Whether you're:

- 🐛 **Reporting bugs**
- 💡 **Suggesting features**
- 📝 **Improving documentation**
- 👨‍💻 **Submitting pull requests**

Every contribution helps make vLLM Router better for everyone.

### Roadmap

- [ ] **v1.1**: Plugin system for custom load balancing algorithms
- [ ] **v1.2**: Web UI for configuration and monitoring
- [ ] **v1.3**: Advanced analytics and reporting
- [ ] **v1.4**: Multi-protocol support (gRPC, WebSocket)
- [ ] **v2.0**: Distributed router clustering

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

### Third-Party Licenses

- **FastAPI**: MIT License
- **Rich**: MIT License
- **aiohttp**: Apache 2.0 License
- **Click**: BSD License

---

## 🙏 Acknowledgments

- [vLLM](https://github.com/vllm-project/vllm) for the amazing LLM inference engine
- [FastAPI](https://fastapi.tiangolo.com/) for the modern web framework
- [Rich](https://github.com/Textualize/rich) for beautiful terminal applications
- The open-source community for inspiration and feedback

---

<div align="center">

**⭐ If vLLM Router helps you solve GPU fragmentation challenges, give us a star!**

[![GitHub Stars](https://img.shields.io/github/stars/xerrors/vllm-router?style=social)](https://github.com/xerrors/vllm-router)

</div>